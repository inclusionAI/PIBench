import { eq } from 'drizzle-orm';
import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db/drizzle';
import { teams } from '@/lib/db/schema';
import { createAlipaySignOrder } from '@/lib/payments/alipay';

export const dynamic = 'force-dynamic';


export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const teamId = Number(body.teamId || 1);
  const amount = String(body.amount || '8.00');
  const planName = String(body.planName || 'Base');

  const [team] = await db.select().from(teams).where(eq(teams.id, teamId)).limit(1);
  if (!team) {
    return NextResponse.json({ error: 'team not found' }, { status: 404 });
  }

  const signOrder = await createAlipaySignOrder({ team, amount, planName });
  await db.update(teams).set({
    alipayExternalAgreementNo: signOrder.externalAgreementNo,
    alipayLastOutTradeNo: signOrder.outTradeNo,
    alipayLastAmount: amount,
    planName,
    subscriptionStatus: 'signing',
    alipayPaymentStatus: 'SIGNING',
    updatedAt: new Date(),
  }).where(eq(teams.id, team.id));

  return NextResponse.json(signOrder);
}
