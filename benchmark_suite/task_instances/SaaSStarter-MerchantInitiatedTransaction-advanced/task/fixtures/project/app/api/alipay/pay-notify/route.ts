import { eq } from 'drizzle-orm';
import { NextRequest } from 'next/server';
import { db } from '@/lib/db/drizzle';
import { teams } from '@/lib/db/schema';
import { verifyAlipayNotify } from '@/lib/payments/alipay';

export const dynamic = 'force-dynamic';

async function readParams(request: NextRequest) {
  const form = await request.formData();
  return Object.fromEntries(Array.from(form.entries()).map(([key, value]) => [key, String(value)]));
}

export async function POST(request: NextRequest) {
  const params = await readParams(request);
  if (!verifyAlipayNotify(params)) {
    return new Response('fail', { status: 400 });
  }

  const outTradeNo = params.out_trade_no;
  if (!outTradeNo) {
    return new Response('fail', { status: 400 });
  }

  const success = params.trade_status === 'TRADE_SUCCESS' || params.trade_status === 'TRADE_FINISHED';
  await db.update(teams).set({
    alipayLastTradeNo: params.trade_no || null,
    alipayLastAmount: params.total_amount || null,
    alipayPaymentStatus: params.trade_status || null,
    subscriptionStatus: success ? 'active' : 'payment_failed',
    updatedAt: new Date(),
  }).where(eq(teams.alipayLastOutTradeNo, outTradeNo));

  return new Response('success');
}
