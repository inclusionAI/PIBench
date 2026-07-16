import { NextRequest, NextResponse } from 'next/server';
import { recipes } from '@/data/recipes';
import {
  createPaymentNeeded,
  parsePaymentProofHeader,
  verifyPaymentWithAlipay,
  sendFulfillmentConfirm,
  createPaymentValidation,
  isAlreadyFulfilled,
  recordFulfillment,
} from '@/lib/a2m';

/**
 * GET /api/recipes/[id] - 食谱详情
 *
 * A2M 智能收流程（对齐 Demo handlePostResource / handleGetResource）：
 * 1. 无 Payment-Proof → 402 Payment Required + Payment-Needed Header
 * 2. 有 Payment-Proof → 解析 → 支付宝验证 → 履约确认 → 返回资源
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const recipeId = parseInt(id, 10);
  const recipe = recipes.find((r) => r.id === recipeId);

  if (!recipe) {
    return NextResponse.json(
      { success: false, error: '食谱不存在' },
      { status: 404 }
    );
  }

  const resourceId = `recipe_${recipe.id}`;
  const resourceName = recipe.name;

  // ========================================
  // Step 1: 检查 Payment-Proof Header
  // ========================================
  const proofHeader = request.headers.get('payment-proof');

  if (!proofHeader) {
    // 无 Payment-Proof → 返回 402 + Payment-Needed
    console.log(`[A2M /api/recipes/${id}] 无 Payment-Proof，返回 402`);
    const { header, body } = createPaymentNeeded(resourceId, resourceName);

    return NextResponse.json(
      {
        success: false,
        code: 'PAYMENT_NEEDED',
        message: '需要支付后查看完整食谱',
        resource_id: resourceId,
        resource_name: resourceName,
        amount: body.protocol.amount,
        currency: body.protocol.currency,
      },
      {
        status: 402,
        headers: { 'Payment-Needed': header },
      }
    );
  }

  // ========================================
  // Step 2: 解析 Payment-Proof
  // ========================================
  console.log(`[A2M /api/recipes/${id}] 收到 Payment-Proof，开始验证`);

  let paymentProof: string;
  let tradeNo: string;
  let clientSession: string | undefined;

  try {
    const parsed = parsePaymentProofHeader(proofHeader);
    paymentProof = parsed.paymentProof;
    tradeNo = parsed.tradeNo;
    clientSession = parsed.clientSession;

    if (!paymentProof || !tradeNo) {
      console.log(`[A2M /api/recipes/${id}] Payment-Proof 缺少必要字段`);
      return NextResponse.json(
        { success: false, code: 'INVALID_PROOF', message: '支付凭证缺少 payment_proof 或 trade_no' },
        { status: 400 }
      );
    }
  } catch (error) {
    console.error(`[A2M /api/recipes/${id}] Payment-Proof 解析失败:`, error);
    return NextResponse.json(
      { success: false, code: 'INVALID_PROOF', message: '支付凭证格式无效' },
      { status: 400 }
    );
  }

  // ========================================
  // Step 3: 防重放检查
  // ========================================
  if (isAlreadyFulfilled(tradeNo)) {
    console.log(`[A2M /api/recipes/${id}] 订单已履约，tradeNo:`, tradeNo.substring(0, 20));
    return NextResponse.json(
      { success: false, code: 'ALREADY_FULFILLED', message: '该订单已完成履约' },
      { status: 409 }
    );
  }

  // ========================================
  // Step 4: 调用支付宝 API 验证支付
  // ========================================
  console.log(`[A2M /api/recipes/${id}] 调用支付宝验证 API`);
  const verifyResult = await verifyPaymentWithAlipay(paymentProof, tradeNo, clientSession);

  if (!verifyResult.verified) {
    console.log(`[A2M /api/recipes/${id}] 支付验证失败:`, verifyResult.error);
    return NextResponse.json(
      {
        success: false,
        code: 'PAYMENT_INVALID',
        message: '支付凭证无效',
        detail: verifyResult.error,
      },
      { status: 402 }
    );
  }

  // ========================================
  // Step 5: 调用支付宝履约确认
  // ========================================
  console.log(`[A2M /api/recipes/${id}] 支付验证通过，发送履约确认`);
  const fulfillResult = await sendFulfillmentConfirm(tradeNo);

  if (!fulfillResult.success) {
    console.warn(`[A2M /api/recipes/${id}] 履约确认失败（仍交付资源）:`, fulfillResult.error);
  }

  // ========================================
  // Step 6: 记录履约 + 生成 Payment-Validation
  // ========================================
  recordFulfillment(tradeNo, resourceId);
  const validationHeader = createPaymentValidation(tradeNo, resourceId);

  // ========================================
  // Step 7: 返回资源
  // ========================================
  console.log(`[A2M /api/recipes/${id}] ✅ 资源交付成功`);

  return NextResponse.json(
    {
      success: true,
      data: recipe,
      payment: {
        trade_no: tradeNo,
        resource_id: resourceId,
        already_fulfilled: false,
      },
    },
    {
      status: 200,
      headers: { 'Payment-Validation': validationHeader },
    }
  );
}
