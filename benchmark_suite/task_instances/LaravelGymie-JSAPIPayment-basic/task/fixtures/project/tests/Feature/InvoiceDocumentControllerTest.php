<?php

use App\Helpers\Helpers;
use App\Models\Invoice;
use App\Models\Member;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Spatie\Permission\Models\Permission;
use Spatie\Permission\PermissionRegistrar;

uses(RefreshDatabase::class);

afterEach(function (): void {
    Helpers::setTestSettingsOverride(null);
});

/**
 * @return array{user: User, invoice: Invoice}
 */
function makeInvoiceWithViewer(): array
{
    Helpers::setTestSettingsOverride([
        'general' => [
            'gym_name' => 'Demo Gym',
            'currency' => 'INR',
        ],
        'charges' => [
            'taxes' => 0,
            'discounts' => [],
        ],
        'subscriptions' => [
            'expiring_days' => 7,
        ],
    ]);

    app(PermissionRegistrar::class)->forgetCachedPermissions();
    Permission::findOrCreate('View:Invoice', 'web');

    $user = User::factory()->create();
    $user->givePermissionTo('View:Invoice');

    $member = Member::factory()->create();
    $plan = Plan::factory()->create([
        'amount' => 1000,
        'days' => 30,
    ]);

    $subscription = Subscription::factory()->create([
        'member_id' => $member->id,
        'plan_id' => $plan->id,
        'start_date' => '2026-02-01',
        'end_date' => '2026-03-01',
    ]);

    $invoice = Invoice::factory()->create([
        'subscription_id' => $subscription->id,
        'date' => '2026-02-20',
        'due_date' => '2026-02-27',
        'subscription_fee' => 1000,
        'discount_amount' => 0,
        'paid_amount' => 0,
    ]);

    return [
        'user' => $user,
        'invoice' => $invoice,
    ];
}

it('forbids invoice preview when the user lacks permission', function (): void {
    Helpers::setTestSettingsOverride([
        'general' => [
            'currency' => 'INR',
        ],
        'charges' => [
            'taxes' => 0,
            'discounts' => [],
        ],
    ]);

    $user = User::factory()->create();

    $member = Member::factory()->create();
    $plan = Plan::factory()->create();
    $subscription = Subscription::factory()->create([
        'member_id' => $member->id,
        'plan_id' => $plan->id,
    ]);
    $invoice = Invoice::factory()->create([
        'subscription_id' => $subscription->id,
        'subscription_fee' => 1000,
        'discount_amount' => 0,
        'paid_amount' => 0,
    ]);

    $this
        ->actingAs($user)
        ->get(route('invoices.preview', $invoice))
        ->assertForbidden();
});

it('renders invoice preview when the user has permission', function (): void {
    ['user' => $user, 'invoice' => $invoice] = makeInvoiceWithViewer();

    $response = $this
        ->actingAs($user)
        ->get(route('invoices.preview', $invoice))
        ->assertOk();

    expect((string) $response->headers->get('content-type'))->toContain('application/pdf');
});

it('downloads the invoice as a PDF when the user has permission', function (): void {
    ['user' => $user, 'invoice' => $invoice] = makeInvoiceWithViewer();

    $response = $this
        ->actingAs($user)
        ->get(route('invoices.download', $invoice))
        ->assertOk();

    expect((string) $response->headers->get('content-type'))->toContain('application/pdf');
});

it('shows a friendly error state when the invoice is missing required data', function (): void {
    ['user' => $user, 'invoice' => $invoice] = makeInvoiceWithViewer();

    $invoice->update([
        'subscription_fee' => 0,
        'discount_amount' => 0,
        'tax' => 0,
        'total_amount' => 0,
        'due_amount' => 0,
        'paid_amount' => 0,
    ]);

    $this
        ->actingAs($user)
        ->get(route('invoices.preview', $invoice))
        ->assertOk()
        ->assertSee(__('app.invoices.error.heading'));

    $this
        ->actingAs($user)
        ->get(route('invoices.download', $invoice))
        ->assertStatus(422)
        ->assertSee(__('app.invoices.error.heading'));
});
