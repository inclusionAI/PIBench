/**
 * A2M 智能收核心库
 * 严格对齐 A2MPaymentDemo.js 官方示例实现
 *
 * 核心流程：
 * 1. 无 Payment-Proof → 返回 402 + Payment-Needed Header
 * 2. 携带 Payment-Proof → 支付宝 API 验证 → 履约确认 → 返回资源
 */

import crypto from 'crypto';

// ============================================================
// 类型定义
// ============================================================

interface A2MConfig {
  appId: string;
  sellerId: string;
  sellerName: string;
  serviceId: string;
  privateKey: string;
  alipayPublicKey: string;
  gateway: string;
  amount: string;
  currency: string;
  keyType: 'PKCS1' | 'PKCS8';
}

interface PaymentNeededProtocol {
  out_trade_no: string;
  amount: string;
  currency: string;
  resource_id: string;
  goods_name: string;
  pay_before: string;
  seller_signature: string;
  seller_sign_type: string;
  seller_unique_id: string;
}

interface PaymentNeededMethod {
  seller_name: string;
  seller_id: string;
  seller_app_id: string;
  goods_name: string;
  seller_unique_id_key: string;
  service_id: string;
}

interface PaymentNeededData {
  protocol: PaymentNeededProtocol;
  method: PaymentNeededMethod;
}

interface PaymentValidationData {
  trade_no: string;
  resource_id: string;
  seller_unique_id: string;
  signature: string;
  sign_type: string;
}

// ============================================================
// 配置管理
// ============================================================

let cachedConfig: A2MConfig | null = null;
let ephemeralKeys: { privateKey: string; publicKey: string } | null = null;

function shouldUseEphemeralTestKeys(): boolean {
  return process.env.A2M_ALLOW_EPHEMERAL_TEST_KEYS === 'true';
}

function getEphemeralTestKeys(): { privateKey: string; publicKey: string } {
  if (!ephemeralKeys) {
    const pair = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
    ephemeralKeys = {
      privateKey: pair.privateKey.export({ type: 'pkcs8', format: 'pem' }).toString(),
      publicKey: pair.publicKey.export({ type: 'spki', format: 'pem' }).toString(),
    };
    console.warn('[A2M] Using ephemeral local test keys. Set real A2M_* keys for integration tests.');
  }

  return ephemeralKeys;
}

function getA2MConfig(): A2MConfig {
  if (cachedConfig) return cachedConfig;

  const privateKey = process.env.A2M_MERCHANT_PRIVATE_KEY || process.env.A2M_PRIVATE_KEY || '';
  const alipayPublicKey = process.env.A2M_ALIPAY_PUBLIC_KEY || '';
  let privateKeySource = 'env';
  let alipayPublicKeySource = 'env';

  // 验证密钥格式
  let validPrivateKey = '';
  if (privateKey) {
    try {
      const pem = normalizeToPEM(privateKey, 'private');
      crypto.createPrivateKey(pem);
      validPrivateKey = pem;
      console.log('[A2M] ✅ 使用 .env.local 中的商户私钥');
    } catch (e) {
      console.error('[A2M] ❌ A2M_MERCHANT_PRIVATE_KEY 格式无效:', (e as Error).message);
    }
  }

  if (!validPrivateKey) {
    if (!privateKey && shouldUseEphemeralTestKeys()) {
      validPrivateKey = getEphemeralTestKeys().privateKey;
      privateKeySource = 'ephemeral-test';
    } else {
      throw new Error('A2M_MERCHANT_PRIVATE_KEY is required and must be a valid RSA private key.');
    }
  }

  let validPublicKey = '';
  if (alipayPublicKey) {
    try {
      const pem = normalizeToPEM(alipayPublicKey, 'public');
      crypto.createPublicKey(pem);
      validPublicKey = pem;
      console.log('[A2M] ✅ 使用 .env.local 中的支付宝公钥');
    } catch (e) {
      console.error('[A2M] ❌ A2M_ALIPAY_PUBLIC_KEY 格式无效:', (e as Error).message);
    }
  }

  if (!validPublicKey) {
    if (!alipayPublicKey && shouldUseEphemeralTestKeys()) {
      validPublicKey = getEphemeralTestKeys().publicKey;
      alipayPublicKeySource = 'ephemeral-test';
    } else {
      throw new Error('A2M_ALIPAY_PUBLIC_KEY is required and must be a valid RSA public key.');
    }
  }

  cachedConfig = {
    appId: process.env.A2M_APP_ID || '',
    sellerId: process.env.A2M_SELLER_ID || process.env.A2M_MERCHANT_ID || '',
    sellerName: process.env.A2M_SELLER_NAME || '宝宝辅食精选',
    serviceId: process.env.A2M_SERVICE_ID || '',
    privateKey: validPrivateKey,
    alipayPublicKey: validPublicKey,
    gateway: process.env.A2M_GATEWAY_URL || process.env.A2M_GATEWAY || '',
    amount: process.env.A2M_PAYMENT_AMOUNT || process.env.A2M_AMOUNT || '0.01',
    currency: process.env.A2M_PAYMENT_CURRENCY || process.env.A2M_CURRENCY || 'CNY',
    keyType: detectKeyType(validPrivateKey),
  };

  console.log('[A2M] 配置加载完成:', {
    appId: cachedConfig.appId,
    sellerId: cachedConfig.sellerId,
    serviceId: cachedConfig.serviceId,
    gateway: cachedConfig.gateway,
    keyType: cachedConfig.keyType,
    privateKeySource,
    alipayPublicKeySource,
  });

  return cachedConfig;
}

// ============================================================
// 密钥工具
// ============================================================

/**
 * 检测私钥格式类型
 * alipay-sdk 需要根据密钥格式传 keyType 参数，否则 formatKey 会损坏密钥
 */
function detectKeyType(key: string): 'PKCS1' | 'PKCS8' {
  const trimmed = key.trim();
  // 从 PEM 头判断
  if (trimmed.includes('-----BEGIN RSA PRIVATE KEY-----')) return 'PKCS1';
  if (trimmed.includes('-----BEGIN PRIVATE KEY-----')) return 'PKCS8';
  // 从 Base64 前缀判断
  // PKCS#8 密钥通常以 MIIEv 开头（包含 AlgorithmIdentifier）
  // PKCS#1 密钥通常以 MIIEp 开头（纯 RSA 模数）
  if (trimmed.startsWith('MIIEv')) return 'PKCS8';
  return 'PKCS1'; // 默认
}

/**
 * 将纯 Base64 或 PEM 字符串标准化为 PEM 格式
 */
function normalizeToPEM(key: string, type: 'private' | 'public'): string {
  const trimmed = key.trim();

  // 已经是 PEM 格式
  if (trimmed.includes('-----BEGIN')) {
    return trimmed;
  }

  // 纯 Base64，需要包装
  const lines = trimmed.match(/.{1,64}/g) || [];
  if (type === 'private') {
    // 根据检测到的密钥类型选择正确的 PEM 头
    const keyType = detectKeyType(trimmed);
    const header = keyType === 'PKCS8' ? 'PRIVATE KEY' : 'RSA PRIVATE KEY';
    return `-----BEGIN ${header}-----\n${lines.join('\n')}\n-----END ${header}-----`;
  } else {
    return `-----BEGIN PUBLIC KEY-----\n${lines.join('\n')}\n-----END PUBLIC KEY-----`;
  }
}

// ============================================================
// Base64URL 编解码（对齐 Demo）
// ============================================================

function base64UrlEncode(data: string): string {
  return Buffer.from(data, 'utf-8')
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function base64UrlDecode(str: string): string {
  let base64 = str.replace(/-/g, '+').replace(/_/g, '/');
  while (base64.length % 4) base64 += '=';
  return Buffer.from(base64, 'base64').toString('utf-8');
}

// ============================================================
// 时间格式化（对齐 Demo）
// ============================================================

/**
 * 格式化为 ISO8601 带时区偏移（+08:00）
 * 对齐 Demo: new Date().toISOString().replace('Z', '+08:00')
 */
function formatISO8601WithTimezone(date: Date): string {
  const pad = (n: number) => n.toString().padStart(2, '0');
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  const seconds = pad(date.getSeconds());
  const offset = -date.getTimezoneOffset();
  const offsetHours = pad(Math.floor(Math.abs(offset) / 60));
  const offsetMinutes = pad(Math.abs(offset) % 60);
  const offsetSign = offset >= 0 ? '+' : '-';
  return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}${offsetSign}${offsetHours}:${offsetMinutes}`;
}

function formatPayBefore(): string {
  // 对齐 Demo: 当前时间 + 30分钟，ISO 8601 带时区偏移量
  const expire = new Date(Date.now() + 30 * 60 * 1000);
  return formatISO8601WithTimezone(expire);
}

// ============================================================
// 订单号生成（对齐 Demo）
// ============================================================

function generateOutTradeNo(): string {
  return `ORDER_${Date.now()}`;
}

// ============================================================
// RSA2 签名（对齐 Demo: crypto.createSign('RSA-SHA256')）
// ============================================================

/**
 * 商户签名 - 对齐 Demo 的 signWithPrivateKey
 * 签名内容为排序后的参数字符串
 */
function signWithPrivateKey(content: string, privateKey: string): string {
  console.log('[A2M] 签名原文:', content);
  const sign = crypto.createSign('RSA-SHA256');
  sign.update(content, 'utf-8');
  const signature = sign.sign(privateKey, 'base64');
  console.log('[A2M] 签名结果:', signature.substring(0, 40) + '...');
  return signature;
}

// ============================================================
// alipay-sdk 实例管理
// ============================================================

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let alipaySdkInstance: any | null = null;
let alipaySdkKeyType: string | null = null;

function getAlipaySdk() {
  const config = getA2MConfig();

  // keyType 变化时需要重建实例（formatKey 依赖 keyType）
  if (alipaySdkInstance && alipaySdkKeyType === config.keyType) return alipaySdkInstance;

  // 动态导入 alipay-sdk（CJS 模块）
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { AlipaySdk } = require('alipay-sdk');

  alipaySdkInstance = new AlipaySdk({
    appId: config.appId,
    privateKey: config.privateKey,
    alipayPublicKey: config.alipayPublicKey,
    gateway: config.gateway,
    signType: 'RSA2',
    charset: 'utf-8',
    timeout: 10000,
    keyType: config.keyType,  // 关键！必须传 keyType，否则 SDK 默认 PKCS1 会损坏 PKCS8 密钥
  });

  console.log('[A2M] alipay-sdk 实例创建成功, keyType:', config.keyType);
  alipaySdkKeyType = config.keyType;
  return alipaySdkInstance;
}

// ============================================================
// 支付记录存储（防重放）
// ============================================================

interface PaymentRecord {
  tradeNo: string;
  resourceId: string;
  fulfilled: boolean;
  timestamp: number;
}

const paymentRecords = new Map<string, PaymentRecord>();

// ============================================================
// 核心：创建 402 Payment-Needed 响应（对齐 Demo handleGetResource 中的 402 逻辑）
// ============================================================

/**
 * 创建 Payment-Needed 数据
 * 对齐 Demo:
 *   protocol = { out_trade_no, amount, currency, resource_id, pay_before, seller_signature, seller_sign_type, seller_unique_id }
 *   method   = { seller_name, seller_id, service_id, min_amount }
 */
export function createPaymentNeeded(
  resourceId: string,
  resourceName: string,
  amount?: string,
  currency?: string
): { header: string; body: PaymentNeededData } {
  const config = getA2MConfig();
  const paymentAmount = amount || config.amount;
  const paymentCurrency = currency || config.currency;
  const outTradeNo = generateOutTradeNo();
  const payBefore = formatPayBefore();

  console.log('[A2M] 创建 Payment-Needed:', { outTradeNo, resourceId, amount: paymentAmount, payBefore });

  // 构造待签名内容 - 对齐 Demo: amount, currency, goods_name, out_trade_no, pay_before, resource_id, seller_id, service_id
  const signParams: Record<string, string> = {
    amount: paymentAmount,
    currency: paymentCurrency,
    goods_name: resourceName,
    out_trade_no: outTradeNo,
    pay_before: payBefore,
    resource_id: resourceId,
    seller_id: config.sellerId,
    service_id: config.serviceId,
  };

  // 按 key 字典序排列，拼接为 key=value&key=value 格式 - 对齐 Demo: Object.keys(params).sort()
  const signContent = Object.keys(signParams).sort().map(key => `${key}=${signParams[key]}`).join('&');

  const sellerSignature = signWithPrivateKey(signContent, config.privateKey);

  const protocol: PaymentNeededProtocol = {
    out_trade_no: outTradeNo,
    amount: paymentAmount,
    currency: paymentCurrency,
    resource_id: resourceId,
    goods_name: resourceName,
    pay_before: payBefore,
    seller_signature: sellerSignature,
    seller_sign_type: 'RSA2',
    seller_unique_id: config.sellerId,
  };

  const method: PaymentNeededMethod = {
    seller_name: config.sellerName,
    seller_id: config.sellerId,
    seller_app_id: config.appId,
    goods_name: resourceName,
    seller_unique_id_key: 'seller_id',
    service_id: config.serviceId,
  };

  const data: PaymentNeededData = { protocol, method };

  // Base64URL 编码 - 对齐 Demo: Buffer.from(JSON.stringify(data)).toString('base64url')
  const header = base64UrlEncode(JSON.stringify(data));

  console.log('[A2M] Payment-Needed Header 生成完成, 长度:', header.length);

  return { header, body: data };
}

// ============================================================
// 核心：验证 Payment-Proof（对齐 Demo handlePostResource）
// ============================================================

/**
 * 解析 Payment-Proof Header
 * 对齐 Demo: base64url 解码 → JSON.parse → 提取 payment_proof / trade_no / client_session
 */
export function parsePaymentProofHeader(proofHeader: string): {
  paymentProof: string;
  tradeNo: string;
  clientSession?: string;
} {
  console.log('[A2M] 解析 Payment-Proof Header, 长度:', proofHeader.length);

  const decoded = base64UrlDecode(proofHeader);
  const proofData = JSON.parse(decoded);
  console.log('[A2M] Base64URL 解码结果顶层 keys:', Object.keys(proofData));

  // 对齐 Demo: payment_proof 和 trade_no 在 protocol 层，client_session 在 method 层
  let paymentProof = '';
  let tradeNo = '';
  let clientSession = '';

  if (proofData.protocol) {
    paymentProof = proofData.protocol.payment_proof || '';
    tradeNo = proofData.protocol.trade_no || '';
    console.log('[A2M] protocol 层 keys:', Object.keys(proofData.protocol));
  }

  if (proofData.method) {
    clientSession = proofData.method.client_session || '';
    console.log('[A2M] method 层 keys:', Object.keys(proofData.method));
  }

  // 降级：如果 protocol 层没找到，尝试从顶层提取
  if (!paymentProof) {
    paymentProof = proofData.payment_proof || proofData.paymentProof || '';
  }
  if (!tradeNo) {
    tradeNo = proofData.trade_no || proofData.tradeNo || proofData.out_trade_no || '';
  }
  if (!clientSession) {
    clientSession = proofData.client_session || proofData.clientSession || '';
  }

  console.log('[A2M] 解析结果:', {
    hasPaymentProof: !!paymentProof,
    hasTradeNo: !!tradeNo,
    tradeNo: tradeNo ? tradeNo.substring(0, 20) + '...' : '(空)',
    hasClientSession: !!clientSession,
  });

  return { paymentProof, tradeNo, clientSession };
}

/**
 * 调用支付宝 API 验证支付凭证
 * 对齐 Demo: alipay.aipay.agent.payment.verify
 *
 * Demo 入参: { payment_proof, trade_no, client_session }
 * Demo 响应校验: code === '10000' && active is True
 */
export async function verifyPaymentWithAlipay(
  paymentProof: string,
  tradeNo: string,
  clientSession?: string
): Promise<{
  verified: boolean;
  active: boolean;
  tradeNo: string;
  rawData?: Record<string, unknown>;
  error?: string;
}> {
  console.log('[A2M] 调用支付宝验证 API:', {
    tradeNo: tradeNo.substring(0, 20) + '...',
    hasPaymentProof: !!paymentProof,
    hasClientSession: !!clientSession,
  });

  try {
    const sdk = getAlipaySdk();

    const bizContent: Record<string, string> = {
      payment_proof: paymentProof,
      trade_no: tradeNo,
    };
    if (clientSession) {
      bizContent.client_session = clientSession;
    }

    console.log('[A2M] verify 请求 bizContent keys:', Object.keys(bizContent));

    const result = await sdk.exec('alipay.aipay.agent.payment.verify', {
      bizContent,
    });

    console.log('[A2M] 支付宝 verify 原始响应:', JSON.stringify(result).substring(0, 500));

    // 兼容嵌套和扁平两种响应结构
    const responseData = result.alipay_aipay_agent_payment_verify_response || result;

    const code = String(responseData.code || '');
    const active = responseData.active === true || responseData.active === 'true';
    const subCode = responseData.sub_code || '';
    const subMsg = responseData.sub_msg || '';

    console.log('[A2M] verify 结果:', { code, active, subCode, subMsg });

    if (code === '10000' && active) {
      console.log('[A2M] ✅ 支付验证通过');
      return { verified: true, active: true, tradeNo, rawData: responseData };
    }

    const errorMsg = subMsg || `code=${code}, active=${active}`;
    console.log('[A2M] ❌ 支付验证失败:', errorMsg);
    return { verified: false, active, tradeNo, rawData: responseData, error: errorMsg };
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : String(error);
    console.error('[A2M] ❌ verify API 调用异常:', errMsg);


    return { verified: false, active: false, tradeNo, error: errMsg };
  }
}

// ============================================================
// 核心：履约确认（对齐 Demo sendFulfillmentConfirm）
// ============================================================

/**
 * 调用支付宝履约确认 API
 * 对齐 Demo: alipay.aipay.agent.fulfillment.confirm
 *
 * Demo 入参: { trade_no }
 */
export async function sendFulfillmentConfirm(
  tradeNo: string
): Promise<{
  success: boolean;
  rawData?: Record<string, unknown>;
  error?: string;
}> {
  console.log('[A2M] 调用履约确认 API, tradeNo:', tradeNo.substring(0, 20) + '...');

  try {
    const sdk = getAlipaySdk();

    const result = await sdk.exec('alipay.aipay.agent.fulfillment.confirm', {
      bizContent: { trade_no: tradeNo },
    });

    console.log('[A2M] 履约确认原始响应:', JSON.stringify(result).substring(0, 500));

    const responseData = result.alipay_aipay_agent_fulfillment_confirm_response || result;
    const code = String(responseData.code || '');

    if (code === '10000') {
      console.log('[A2M] ✅ 履约确认成功');
      return { success: true, rawData: responseData };
    }

    const subMsg = responseData.sub_msg || `code=${code}`;
    console.log('[A2M] ❌ 履约确认失败:', subMsg);
    return { success: false, rawData: responseData, error: subMsg };
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : String(error);
    console.error('[A2M] ❌ 履约确认 API 异常:', errMsg);


    return { success: false, error: errMsg };
  }
}

// ============================================================
// 核心：创建 Payment-Validation Header（对齐 Demo）
// ============================================================

/**
 * 创建 Payment-Validation Header
 * 对齐 Demo: 在资源交付后返回给客户端的验证头
 */
export function createPaymentValidation(
  tradeNo: string,
  resourceId: string
): string {
  const config = getA2MConfig();

  // 签名内容
  const signContent = `resource_id=${resourceId}&trade_no=${tradeNo}`;
  const signature = signWithPrivateKey(signContent, config.privateKey);

  const validationData: PaymentValidationData = {
    trade_no: tradeNo,
    resource_id: resourceId,
    seller_unique_id: config.sellerId,
    signature,
    sign_type: 'RSA2',
  };

  const header = base64UrlEncode(JSON.stringify(validationData));
  console.log('[A2M] Payment-Validation Header 生成完成, 长度:', header.length);
  return header;
}

// ============================================================
// 防重放检查
// ============================================================

export function isAlreadyFulfilled(tradeNo: string): boolean {
  return paymentRecords.has(tradeNo) && paymentRecords.get(tradeNo)!.fulfilled;
}

export function recordFulfillment(tradeNo: string, resourceId: string): void {
  paymentRecords.set(tradeNo, { tradeNo, resourceId, fulfilled: true, timestamp: Date.now() });
  console.log('[A2M] 记录履约:', { tradeNo: tradeNo.substring(0, 20) + '...', resourceId });
}

// ============================================================
// 导出工具函数供外部使用
// ============================================================

export { base64UrlEncode, base64UrlDecode };
export type { PaymentNeededData, PaymentValidationData };
