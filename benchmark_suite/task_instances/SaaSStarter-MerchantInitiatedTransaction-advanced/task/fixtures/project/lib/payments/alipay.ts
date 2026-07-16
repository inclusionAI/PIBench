import { AlipaySdk } from 'alipay-sdk';
import type { Team } from '@/lib/db/schema';

type AlipayCommonResult = Record<string, any>;

type SignOrderInput = {
  team: Team;
  amount: string;
  planName: string;
};

type WithholdInput = {
  team: Team;
  amount: string;
  subject?: string;
};

const GENERAL_WITHHOLDING = 'GENERAL_WITHHOLDING';
const PERSONAL_PRODUCT_CODE = 'CYCLE_PAY_AUTH_P';
const APP_PAY_PRODUCT_CODE = 'QUICK_MSECURITY_PAY';

function env(name: string, fallback?: string) {
  const value = process.env[name] ?? fallback;
  if (!value) {
    throw new Error(`${name} is required for Alipay integration`);
  }
  return value;
}

export function isAlipayMockMode() {
  return process.env.ALIPAY_MOCK_MODE === 'true';
}

export function getBaseUrl() {
  return env('BASE_URL', 'http://127.0.0.1:3000');
}

function getSdk() {
  return new AlipaySdk({
    appId: env('ALIPAY_APP_ID'),
    privateKey: env('ALIPAY_PRIVATE_KEY'),
    alipayPublicKey: env('ALIPAY_PUBLIC_KEY'),
    gateway: env('ALIPAY_GATEWAY', 'https://openapi.alipay.com/gateway.do'),
    signType: 'RSA2',
  });
}

function normalizeAmount(amount: string) {
  const parsed = Number(amount);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    throw new Error('amount must be a positive number');
  }
  return parsed.toFixed(2);
}

function timestamp() {
  return new Date().toISOString().replace('T', ' ').slice(0, 19);
}

function responseKey(method: string) {
  return `${method.replace(/\./g, '_')}_response`;
}

async function mockGatewayRequest(method: string, bizContent: Record<string, any>) {
  const body = new URLSearchParams({
    method,
    app_id: env('ALIPAY_APP_ID', 'case_mock_app'),
    charset: 'UTF-8',
    sign_type: 'RSA2',
    timestamp: timestamp(),
    version: '1.0',
    biz_content: JSON.stringify(bizContent),
  });

  const response = await fetch(env('ALIPAY_GATEWAY', 'http://127.0.0.1:4100/gateway.do'), {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!response.ok) {
    throw new Error(`mock Alipay gateway failed with HTTP ${response.status}`);
  }
  const payload = await response.json() as Record<string, any>;
  return (payload[responseKey(method)] || payload) as AlipayCommonResult;
}

export function newExternalAgreementNo(teamId: number) {
  return `T${teamId}${Date.now()}`.slice(0, 32);
}

export function newOutTradeNo(prefix: string, teamId: number) {
  return `${prefix}${teamId}${Date.now()}`.slice(0, 64);
}

export async function createAlipaySignOrder({ team, amount, planName }: SignOrderInput) {
  const normalizedAmount = normalizeAmount(amount);
  const baseUrl = getBaseUrl();
  const externalAgreementNo = newExternalAgreementNo(team.id);
  const outTradeNo = newOutTradeNo('SIGN', team.id);
  const signNotifyUrl = `${baseUrl}/api/alipay/sign-notify`;
  const notifyUrl = `${baseUrl}/api/alipay/pay-notify`;
  const bizContent = {
    out_trade_no: outTradeNo,
    total_amount: normalizedAmount,
    subject: `${planName} membership subscription`,
    product_code: APP_PAY_PRODUCT_CODE,
    agreement_sign_params: {
      access_params: {
        channel: process.env.ALIPAY_SIGN_CHANNEL || 'QRCODE',
      },
      period_rule_params: {
        period: Number(process.env.ALIPAY_PERIOD || '1'),
        single_amount: normalizedAmount,
        period_type: process.env.ALIPAY_PERIOD_TYPE || 'MONTH',
      },
      sign_notify_url: signNotifyUrl,
      external_agreement_no: externalAgreementNo,
      personal_product_code: PERSONAL_PRODUCT_CODE,
      product_code: GENERAL_WITHHOLDING,
      sign_scene: process.env.ALIPAY_SIGN_SCENE || 'INDUSTRY|DIGITAL_MEDIA',
    },
  };

  if (isAlipayMockMode()) {
    const result = await mockGatewayRequest('alipay.trade.app.pay', {
      ...bizContent,
      notify_url: notifyUrl,
    });
    const orderString = result.order_string || `mock_order_string:${outTradeNo}:${externalAgreementNo}`;
    return {
      mode: 'mock-server',
      outTradeNo,
      externalAgreementNo,
      orderString,
      qrCodeContent: result.qr_code_content || `alipays://platformapi/startApp?appId=60000157&orderStr=${encodeURIComponent(orderString)}`,
      request: { method: 'alipay.trade.app.pay', notifyUrl, signNotifyUrl, bizContent },
      gatewayResult: result,
    };
  }

  const orderString = getSdk().sdkExecute('alipay.trade.app.pay', {
    notifyUrl,
    bizContent,
  });

  return {
    mode: 'sdk',
    outTradeNo,
    externalAgreementNo,
    orderString,
    qrCodeContent: `alipays://platformapi/startApp?appId=60000157&orderStr=${encodeURIComponent(orderString)}`,
    request: { method: 'alipay.trade.app.pay', notifyUrl, signNotifyUrl, bizContent },
  };
}

export async function executeAlipayWithholding({ team, amount, subject }: WithholdInput) {
  const normalizedAmount = normalizeAmount(amount);
  if (!team.alipayAgreementNo) {
    throw new Error('team does not have an Alipay agreement number');
  }

  const outTradeNo = newOutTradeNo('DEDUCT', team.id);
  const notifyUrl = `${getBaseUrl()}/api/alipay/pay-notify`;
  const bizContent = {
    out_trade_no: outTradeNo,
    total_amount: normalizedAmount,
    subject: subject || `${team.planName || 'Membership'} recurring charge`,
    product_code: GENERAL_WITHHOLDING,
    agreement_params: {
      agreement_no: team.alipayAgreementNo,
    },
    seller_id: process.env.ALIPAY_SELLER_ID || process.env.ALIPAY_PID,
    pay_params: {
      async_type: 'NORMAL_ASYNC',
    },
    query_options: ['fund_bill_list'],
    notify_url: notifyUrl,
  };

  if (isAlipayMockMode()) {
    const result = await mockGatewayRequest('alipay.trade.pay', bizContent);
    return { outTradeNo, result };
  }

  const result = await getSdk().exec('alipay.trade.pay', {
    notifyUrl,
    bizContent,
  }) as AlipayCommonResult;
  return { outTradeNo, result };
}

export function verifyAlipayNotify(params: Record<string, string>) {
  if (isAlipayMockMode() && process.env.ALIPAY_ALLOW_UNSIGNED_NOTIFY === 'true') {
    return true;
  }
  return getSdk().checkNotifySignV2(params);
}
