import { stripe } from '../payments/stripe';
import { db } from './drizzle';
import { users, teams, teamMembers } from './schema';
import { hashPassword } from '@/lib/auth/session';
import { and, eq } from 'drizzle-orm';

async function createStripeProducts() {
  console.log('Creating Stripe products and prices...');

  const baseProduct = await stripe.products.create({
    name: 'Base',
    description: 'Base subscription plan',
  });

  await stripe.prices.create({
    product: baseProduct.id,
    unit_amount: 800, // $8 in cents
    currency: 'usd',
    recurring: {
      interval: 'month',
      trial_period_days: 7,
    },
  });

  const plusProduct = await stripe.products.create({
    name: 'Plus',
    description: 'Plus subscription plan',
  });

  await stripe.prices.create({
    product: plusProduct.id,
    unit_amount: 1200, // $12 in cents
    currency: 'usd',
    recurring: {
      interval: 'month',
      trial_period_days: 7,
    },
  });

  console.log('Stripe products and prices created successfully.');
}

async function seed() {
  const email = 'test@test.com';
  const password = 'admin123';
  const passwordHash = await hashPassword(password);
  const now = new Date();

  let [user] = await db.select().from(users).where(eq(users.email, email)).limit(1);
  if (user) {
    [user] = await db
      .update(users)
      .set({
        passwordHash,
        role: 'owner',
        deletedAt: null,
        updatedAt: now,
      })
      .where(eq(users.id, user.id))
      .returning();
  } else {
    [user] = await db
      .insert(users)
      .values({
        email,
        passwordHash,
        role: 'owner',
      })
      .returning();
  }

  console.log(`Seed user ready: ${email} / ${password} / owner.`);

  let [team] = await db.select().from(teams).where(eq(teams.name, 'Test Team')).limit(1);
  if (team) {
    [team] = await db
      .update(teams)
      .set({
        planName: 'Base',
        subscriptionStatus: 'mock_ready',
        alipayExternalAgreementNo: null,
        alipayAgreementNo: null,
        alipayBuyerUserId: null,
        alipayLastOutTradeNo: null,
        alipayLastTradeNo: null,
        alipayLastAmount: null,
        alipayPaymentStatus: 'READY',
        alipayNextDeductTime: null,
        updatedAt: now,
      })
      .where(eq(teams.id, team.id))
      .returning();
  } else {
    [team] = await db
      .insert(teams)
      .values({
        name: 'Test Team',
        planName: 'Base',
        subscriptionStatus: 'mock_ready',
        alipayPaymentStatus: 'READY',
      })
      .returning();
  }

  const [membership] = await db
    .select()
    .from(teamMembers)
    .where(and(eq(teamMembers.teamId, team.id), eq(teamMembers.userId, user.id)))
    .limit(1);
  if (membership) {
    await db
      .update(teamMembers)
      .set({ role: 'owner' })
      .where(eq(teamMembers.id, membership.id));
  } else {
    await db.insert(teamMembers).values({
      teamId: team.id,
      userId: user.id,
      role: 'owner',
    });
  }
  console.log('Seed team ready: Test Team / Base / mock_ready / Alipay READY.');

  if (process.env.SKIP_STRIPE_SEED === "true") {
    console.log("Skipping Stripe product seed for local case startup.");
  } else {
    await createStripeProducts();
  }
}

seed()
  .catch((error) => {
    console.error('Seed process failed:', error);
    process.exit(1);
  })
  .finally(() => {
    console.log('Seed process finished. Exiting...');
    process.exit(0);
  });
