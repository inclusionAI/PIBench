<?php

use App\Contracts\SettingsRepository;
use App\Jobs\SendInvoiceIssuedEmail;
use App\Jobs\SendInvoicePaymentReceiptEmail;
use App\Models\Expense;
use App\Models\Invoice;
use App\Models\InvoiceTransaction;
use App\Models\Member;
use App\Models\Plan;
use App\Models\Subscription;
use Database\Seeders\DashboardDemoSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\Queue;

uses(RefreshDatabase::class);

test('dashboard demo seeder creates enough data for analytics widgets', function (): void {
    $this->seed(DashboardDemoSeeder::class);

    expect(Member::query()->count())->toBeGreaterThanOrEqual(200);
    expect(Subscription::query()->count())->toBeGreaterThanOrEqual(200);
    expect(Invoice::query()->count())->toBeGreaterThanOrEqual(200);
    expect(InvoiceTransaction::query()->count())->toBeGreaterThan(0);
    expect(Expense::query()->count())->toBeGreaterThanOrEqual(150);
});

test('dashboard demo seeder avoids invoice number collisions with trashed invoices', function (): void {
    $plan = Plan::factory()->create([
        'amount' => 100,
        'days' => 30,
    ]);

    $subscriptionA = Subscription::factory()
        ->for(Member::factory())
        ->for($plan)
        ->create();

    $subscriptionB = Subscription::factory()
        ->for(Member::factory())
        ->for($plan)
        ->create();

    $trashedInvoice = Invoice::query()->create([
        'number' => 'GY-1',
        'subscription_id' => $subscriptionB->id,
        'date' => now()->toDateString(),
        'due_date' => now()->addDays(7)->toDateString(),
        'payment_method' => 'offline',
        'status' => 'issued',
        'subscription_fee' => 100,
        'discount_amount' => 0,
        'paid_amount' => 0,
    ]);

    $trashedInvoice->delete();

    $seeder = new DashboardDemoSeeder;

    $method = new ReflectionMethod($seeder, 'seedInvoicesForSubscriptions');
    $method->setAccessible(true);
    $method->invoke($seeder, new Collection([$subscriptionA]), new Collection([$plan]));

    $invoiceA = Invoice::query()->where('subscription_id', $subscriptionA->id)->firstOrFail();

    expect((string) $invoiceA->number)->not->toBe('GY-1');
});

test('dashboard demo seeder does not queue invoice emails', function (): void {
    Queue::fake();

    $settingsRepository = app(SettingsRepository::class);
    $settings = $settingsRepository->get();

    data_set($settings, 'notifications.email.enabled', true);
    data_set($settings, 'notifications.email.auto_send_invoice_issued', true);
    data_set($settings, 'notifications.email.auto_send_payment_receipt', true);

    $settingsRepository->put($settings);

    $this->seed(DashboardDemoSeeder::class);

    Queue::assertNotPushed(SendInvoiceIssuedEmail::class);
    Queue::assertNotPushed(SendInvoicePaymentReceiptEmail::class);
});
