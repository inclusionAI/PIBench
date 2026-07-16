<?php

use App\Helpers\Helpers;
use App\Models\Invoice;
use App\Models\Member;
use App\Models\Plan;
use App\Models\Subscription;
use Carbon\Carbon;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

beforeEach(function (): void {
    Helpers::setTestSettingsOverride([
        'general' => [
            'currency' => 'INR',
        ],
        'charges' => [
            'taxes' => 10,
            'discounts' => [],
        ],
        'subscriptions' => [
            'expiring_days' => 7,
        ],
        'payments' => [
            'provider' => 'stripe',
        ],
        'notifications' => [
            'email' => [],
        ],
    ]);
});

afterEach(function (): void {
    Helpers::setTestSettingsOverride(null);
});

it('keeps subscription_fee as gross and computes tax/total from settings', function (): void {
    config()->set('app.timezone', 'UTC');
    Carbon::setTestNow(Carbon::parse('2026-03-02 10:00:00', 'UTC'));

    $member = Member::factory()->create();
    $plan = Plan::factory()->create([
        'amount' => 1000,
        'days' => 30,
    ]);

    $subscription = Subscription::factory()->create([
        'member_id' => $member->id,
        'plan_id' => $plan->id,
        'start_date' => '2026-03-01',
        'end_date' => '2026-03-31',
    ]);

    $invoice = Invoice::factory()->create([
        'subscription_id' => $subscription->id,
        'subscription_fee' => 1000,
        'discount_amount' => 100,
        'paid_amount' => 200,
        'date' => '2026-03-01',
        'due_date' => '2026-03-08',
    ])->refresh();

    expect((float) $invoice->subscription_fee)->toBe(1000.0);
    expect((float) $invoice->discount_amount)->toBe(100.0);
    expect((float) $invoice->tax)->toBe(100.0);
    expect((float) $invoice->total_amount)->toBe(1000.0);
    expect((float) $invoice->paid_amount)->toBe(200.0);
    expect((float) $invoice->due_amount)->toBe(800.0);
    expect($invoice->status?->value)->toBe('partial');
});
