import { eq } from 'drizzle-orm';
import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db/drizzle';
import { teams } from '@/lib/db/schema';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const teamId = Number(request.nextUrl.searchParams.get('teamId') || 1);
  const [team] = await db.select().from(teams).where(eq(teams.id, teamId)).limit(1);
  if (!team) {
    return NextResponse.json({ error: 'team not found' }, { status: 404 });
  }
  return NextResponse.json({
    id: team.id,
    name: team.name,
    planName: team.planName,
    subscriptionStatus: team.subscriptionStatus,
    alipayExternalAgreementNo: team.alipayExternalAgreementNo,
    alipayAgreementNo: team.alipayAgreementNo,
    alipayBuyerUserId: team.alipayBuyerUserId,
    alipayLastOutTradeNo: team.alipayLastOutTradeNo,
    alipayLastTradeNo: team.alipayLastTradeNo,
    alipayLastAmount: team.alipayLastAmount,
    alipayPaymentStatus: team.alipayPaymentStatus,
    alipayNextDeductTime: team.alipayNextDeductTime,
  });
}
