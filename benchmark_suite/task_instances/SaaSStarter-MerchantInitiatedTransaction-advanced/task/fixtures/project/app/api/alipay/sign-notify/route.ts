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

  const externalAgreementNo = params.external_agreement_no;
  if (!externalAgreementNo) {
    return new Response('fail', { status: 400 });
  }

  await db.update(teams).set({
    alipayAgreementNo: params.agreement_no || null,
    alipayBuyerUserId: params.alipay_user_id || params.alipay_open_id || null,
    alipayNextDeductTime: params.next_deduct_time || null,
    alipayPaymentStatus: params.status || 'NORMAL',
    subscriptionStatus: params.status === 'NORMAL' ? 'active' : 'incomplete',
    updatedAt: new Date(),
  }).where(eq(teams.alipayExternalAgreementNo, externalAgreementNo));

  return new Response('success');
}
