<?php

namespace Database\Seeders;

use App\Contracts\SettingsRepository;
use App\Helpers\Helpers;
use App\Models\Expense;
use App\Models\Invoice;
use App\Models\InvoiceTransaction;
use App\Models\Member;
use App\Models\Plan;
use App\Models\Service;
use App\Models\Subscription;
use App\Models\User;
use Carbon\CarbonImmutable;
use Illuminate\Database\Seeder;
use Illuminate\Support\Collection;

class DashboardDemoSeeder extends Seeder
{
    /**
     * Seed a realistic dataset for the dashboard (dev only).
     *
     * This intentionally creates enough records for charts/tables to look real:
     * - Members: 200+
     * - Subscriptions: ~220 (includes renewals)
     * - Invoices: one per subscription
     * - Invoice transactions: multiple payments + some refunds
     * - Expenses: 150+
     */
    public function run(): void
    {
        $timezone = config('app.timezone');
        $faker = fake();

        $this->ensureMinimumCount(Service::class, 8, fn (int $count): Collection => Service::factory()->count($count)->create());
        $this->ensureMinimumCount(Plan::class, 10, fn (int $count): Collection => Plan::factory()->count($count)->create());

        $this->ensureMinimumCount(Member::class, 200, function (int $count) use ($faker, $timezone): Collection {
            return Member::factory()
                ->count($count)
                ->state(fn (): array => [
                    'created_at' => CarbonImmutable::instance($faker->dateTimeBetween('-12 months', 'now', $timezone)),
                ])
                ->create();
        });

        $plans = Plan::query()->get();
        $members = Member::query()->inRandomOrder()->limit(200)->get();

        $this->withoutInvoiceEmails(function () use ($members, $plans): void {
            $this->seedSubscriptionsForMembers($members, $plans);
            $this->seedInvoicesForSubscriptions($this->subscriptionsNeedingInvoices(), $plans);
        });

        $this->ensureMinimumCount(Expense::class, 150, fn (int $count): Collection => Expense::factory()->count($count)->create());
    }

    /**
     * Ensure a model has at least the given number of rows.
     *
     * @template TModel of \Illuminate\Database\Eloquent\Model
     *
     * @param  class-string<TModel>  $modelClass
     * @param  callable(int):Collection<int,TModel>  $factory
     */
    private function ensureMinimumCount(string $modelClass, int $minimum, callable $factory): void
    {
        $current = $modelClass::query()->count();

        if ($current >= $minimum) {
            return;
        }

        $factory($minimum - $current);
    }

    /**
     * Create subscriptions across different date buckets so dashboard widgets have variety.
     *
     * @param  Collection<int, Member>  $members
     * @param  Collection<int, Plan>  $plans
     */
    private function seedSubscriptionsForMembers(Collection $members, Collection $plans): void
    {
        $timezone = config('app.timezone');
        $today = CarbonImmutable::today($timezone);
        $expiringEnd = $today->addDays(Helpers::getSubscriptionExpiringDays());

        $created = 0;

        foreach ($members as $member) {
            if ($member->subscriptions()->exists()) {
                continue;
            }

            $plan = $plans->random();

            [$startDate, $endDate] = match (true) {
                $created < 20 => [
                    $today->subDays(random_int(25, 120)),
                    $today->subDays(random_int(1, 30)),
                ],
                $created < 50 => [
                    $today->subDays(random_int(5, 90)),
                    CarbonImmutable::instance(fake()->dateTimeBetween($today->toDateString(), $expiringEnd->toDateString(), $timezone))->startOfDay(),
                ],
                $created < 190 => [
                    $today->subDays(random_int(10, 120)),
                    $today->addDays(random_int(10, 180)),
                ],
                default => [
                    $today->addDays(random_int(1, 20)),
                    $today->addDays(random_int(30, 240)),
                ],
            };

            if ($endDate->lessThanOrEqualTo($startDate)) {
                $endDate = $startDate->addDays(max(1, (int) $plan->days));
            }

            Subscription::query()->create([
                'member_id' => $member->id,
                'plan_id' => $plan->id,
                'start_date' => $startDate->toDateString(),
                'end_date' => $endDate->toDateString(),
                'status' => $this->statusForSubscriptionDates($startDate, $endDate, $today, $expiringEnd),
            ]);

            $created++;
        }

        $this->seedRenewals($today, $plans);
    }

    /**
     * Create renewal subscriptions for a subset of expired subscriptions.
     *
     * @param  Collection<int, Plan>  $plans
     */
    private function seedRenewals(CarbonImmutable $today, Collection $plans): void
    {
        $expiringEnd = $today->addDays(Helpers::getSubscriptionExpiringDays());

        $expiredSubscriptions = Subscription::query()
            ->whereDate('end_date', '<', $today->toDateString())
            ->whereDoesntHave('renewals')
            ->inRandomOrder()
            ->limit(20)
            ->get();

        foreach ($expiredSubscriptions as $expired) {
            $plan = $plans->random();
            $start = CarbonImmutable::parse($expired->end_date, config('app.timezone'))->addDay()->startOfDay();
            $end = $start->addDays(max(1, (int) $plan->days));

            Subscription::query()->create([
                'renewed_from_subscription_id' => $expired->id,
                'member_id' => $expired->member_id,
                'plan_id' => $plan->id,
                'start_date' => $start->toDateString(),
                'end_date' => $end->toDateString(),
                'status' => $this->statusForSubscriptionDates($start, $end, $today, $expiringEnd),
            ]);
        }
    }

    /**
     * Determine a subscription status based on dates (keeps status consistent with the UI).
     */
    private function statusForSubscriptionDates(
        CarbonImmutable $start,
        CarbonImmutable $end,
        CarbonImmutable $today,
        CarbonImmutable $expiringEnd,
    ): string {
        if ($start->greaterThan($today)) {
            return 'upcoming';
        }

        if ($end->lessThan($today)) {
            return 'expired';
        }

        if ($end->lessThanOrEqualTo($expiringEnd)) {
            return 'expiring';
        }

        return 'ongoing';
    }

    /**
     * Subscriptions which don't yet have an invoice.
     *
     * Note: invoice is unique per subscription.
     *
     * @return Collection<int, Subscription>
     */
    private function subscriptionsNeedingInvoices(): Collection
    {
        return Subscription::query()
            ->whereDoesntHave('invoices', fn ($query) => $query->withTrashed())
            ->with(['plan'])
            ->get();
    }

    /**
     * Create one invoice per subscription, plus ledger transactions spread across time.
     *
     * @param  Collection<int, Subscription>  $subscriptions
     * @param  Collection<int, Plan>  $plans
     */
    private function seedInvoicesForSubscriptions(Collection $subscriptions, Collection $plans): void
    {
        $timezone = config('app.timezone');
        $faker = fake();
        $staffUserId = User::query()->value('id');
        $nextInvoiceNumber = $this->nextDemoInvoiceSequenceNumber();
        $invoicePrefix = $this->demoInvoicePrefix();

        foreach ($subscriptions as $subscription) {
            $plan = $subscription->plan ?? $plans->random();
            $startDate = CarbonImmutable::parse($subscription->start_date, $timezone)->startOfDay();

            $invoiceDate = $startDate;
            $dueDate = $invoiceDate->addDays(7);

            $grossFee = (float) ($plan->amount ?? 0);
            $discountAmount = $faker->boolean(35) ? round($grossFee * $faker->randomFloat(2, 0.02, 0.15), 2) : 0.0;

            while (Invoice::withTrashed()->where('number', "{$invoicePrefix}-{$nextInvoiceNumber}")->exists()) {
                $nextInvoiceNumber++;
            }

            $invoice = Invoice::query()->create([
                'number' => "{$invoicePrefix}-{$nextInvoiceNumber}",
                'subscription_id' => $subscription->id,
                'date' => $invoiceDate->toDateString(),
                'due_date' => $dueDate->toDateString(),
                'payment_method' => $faker->boolean(70) ? 'offline' : 'online',
                'status' => 'issued',
                'subscription_fee' => $grossFee,
                'discount_amount' => $discountAmount,
                'discount_note' => $discountAmount > 0 ? 'Promo discount' : null,
                'paid_amount' => 0,
            ]);

            $nextInvoiceNumber++;

            $this->seedTransactionsForInvoice($invoice, $invoiceDate, $staffUserId);
        }
    }

    /**
     * Get a stable invoice prefix for demo seeding.
     */
    private function demoInvoicePrefix(): string
    {
        $rawPrefix = (string) data_get(Helpers::getSettings(), 'invoice.prefix', '');
        $prefix = trim($rawPrefix, '-');

        return filled($prefix) ? $prefix : 'GY';
    }

    /**
     * Determine the next numeric suffix to use for demo invoices.
     */
    private function nextDemoInvoiceSequenceNumber(): int
    {
        $max = Invoice::withTrashed()
            ->pluck('number')
            ->map(function (string $number): int {
                if (preg_match('/(\\d+)$/', $number, $matches) !== 1) {
                    return 0;
                }

                return (int) $matches[1];
            })
            ->max();

        return ((int) $max) + 1;
    }

    /**
     * Seed payment/refund transactions for an invoice so trends look realistic.
     */
    private function seedTransactionsForInvoice(Invoice $invoice, CarbonImmutable $invoiceDate, ?int $staffUserId): void
    {
        $faker = fake();
        $timezone = config('app.timezone');

        $total = max((float) $invoice->total_amount, 0);
        if ($total <= 0) {
            return;
        }

        $scenario = $faker->randomElement([
            'paid', 'paid', 'paid', 'paid',
            'partial', 'partial',
            'issued',
            'refund',
        ]);

        $paymentMethod = $invoice->payment_method === 'online' ? 'stripe' : 'offline';

        if ($scenario === 'issued') {
            $invoice->syncFromTransactions();

            return;
        }

        $paymentsTarget = match ($scenario) {
            'paid', 'refund' => $total,
            default => round($total * $faker->randomFloat(2, 0.1, 0.8), 2),
        };

        $paymentsTarget = min(max($paymentsTarget, 0), $total);

        $paymentsCount = $scenario === 'partial' ? $faker->numberBetween(1, 3) : $faker->numberBetween(1, 2);
        $remaining = $paymentsTarget;

        for ($i = 0; $i < $paymentsCount; $i++) {
            $amount = $i === $paymentsCount - 1
                ? $remaining
                : round($remaining * $faker->randomFloat(2, 0.2, 0.7), 2);

            $remaining = round($remaining - $amount, 2);

            if ($amount <= 0) {
                continue;
            }

            $occurredAt = CarbonImmutable::instance($faker->dateTimeBetween(
                $invoiceDate->toDateString(),
                $invoiceDate->addDays(30)->toDateString(),
                $timezone,
            ));

            InvoiceTransaction::query()->create([
                'invoice_id' => $invoice->id,
                'type' => 'payment',
                'amount' => $amount,
                'occurred_at' => $occurredAt,
                'payment_method' => $paymentMethod,
                'note' => $scenario === 'partial' ? 'Partial payment' : 'Payment received',
                'reference_id' => null,
                'created_by' => $staffUserId,
            ]);
        }

        if ($scenario === 'refund') {
            $refundable = (float) $invoice->transactions()->where('type', 'payment')->sum('amount');
            $refundAmount = round($refundable * $faker->randomFloat(2, 0.2, 1.0), 2);
            $refundAmount = min(max($refundAmount, 0), $refundable);

            if ($refundAmount > 0) {
                $occurredAt = CarbonImmutable::instance($faker->dateTimeBetween(
                    $invoiceDate->addDays(3)->toDateString(),
                    $invoiceDate->addDays(60)->toDateString(),
                    $timezone,
                ));

                InvoiceTransaction::query()->create([
                    'invoice_id' => $invoice->id,
                    'type' => 'refund',
                    'amount' => $refundAmount,
                    'occurred_at' => $occurredAt,
                    'payment_method' => $paymentMethod,
                    'note' => 'Refund processed',
                    'reference_id' => null,
                    'created_by' => $staffUserId,
                ]);
            }
        }

        $invoice->syncFromTransactions();
    }

    /**
     * Disable invoice-related email notifications while demo data is generated.
     */
    private function withoutInvoiceEmails(callable $callback): void
    {
        $settingsRepository = app(SettingsRepository::class);
        $settings = $settingsRepository->get();

        $originalEmailSettings = data_get($settings, 'notifications.email', []);

        data_set($settings, 'notifications.email.enabled', false);
        data_set($settings, 'notifications.email.auto_send_invoice_issued', false);
        data_set($settings, 'notifications.email.auto_send_payment_receipt', false);

        $settingsRepository->put($settings);

        try {
            $callback();
        } finally {
            data_set($settings, 'notifications.email', is_array($originalEmailSettings) ? $originalEmailSettings : []);
            $settingsRepository->put($settings);
        }
    }
}
