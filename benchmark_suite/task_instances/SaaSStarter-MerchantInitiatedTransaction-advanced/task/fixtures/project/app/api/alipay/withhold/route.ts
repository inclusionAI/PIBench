import { eq } from 'drizzle-orm';
import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db/drizzle';
import { teams } from '@/lib/db/schema';
import { executeAlipayWithholding } from '@/lib/payments/alipay';

export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const teamId = Number(body.teamId || 1);
  const amount = String(body.amount || '8.00');

  const [team] = await db.select().from(teams).where(eq(teams.id, teamId)).limit(1);
  if (!team) {
    return NextResponse.json({ error: 'team not found' }, { status: 404 });
  }
  if (!team.alipayAgreementNo) {
    return NextResponse.json({ error: 'team has no active Alipay agreement' }, { status: 409 });
  }

  const { outTradeNo, result } = await executeAlipayWithholding({ team, amount });
  await db.update(teams).set({
    alipayLastOutTradeNo: outTradeNo,
    alipayLastTradeNo: result.trade_no || null,
    alipayLastAmount: amount,
    alipayPaymentStatus: result.code === '10000' ? 'TRADE_SUCCESS' : result.code === '10003' ? 'ACCEPTED' : 'FAILED',
    subscriptionStatus: result.code === '10000' || result.code === '10003' ? 'active' : 'deducting',
    updatedAt: new Date(),
  }).where(eq(teams.id, team.id));

  return NextResponse.json({ outTradeNo, result });
}
