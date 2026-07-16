<?php

use App\Filament\Widgets\Analytics\MembershipMetricsWidget;
use App\Helpers\Helpers;
use App\Models\Member;
use App\Models\Plan;
use App\Models\Subscription;
use Carbon\CarbonImmutable;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;

uses(RefreshDatabase::class);

afterEach(function (): void {
    Helpers::setTestSettingsOverride(null);
});

it('does not show an expiring badge on the active members card', function (): void {
    config()->set('app.timezone', 'UTC');
    CarbonImmutable::setTestNow(CarbonImmutable::parse('2026-02-23', 'UTC'));

    Helpers::setTestSettingsOverride([
        'general' => [
            'currency' => 'INR',
        ],
        'charges' => [
            'taxes' => 0,
            'discounts' => [],
        ],
        'subscriptions' => [
            'expiring_days' => 7,
        ],
        'payments' => [
            'provider' => 'stripe',
        ],
    ]);

    $member = Member::factory()->create([
        'created_at' => '2026-02-10 10:00:00',
    ]);

    $plan = Plan::factory()->create([
        'days' => 30,
        'amount' => 1000,
    ]);

    Subscription::factory()->create([
        'member_id' => $member->id,
        'plan_id' => $plan->id,
        'start_date' => '2026-02-01',
        'end_date' => '2026-03-01',
        'status' => 'ongoing',
    ]);

    Livewire::test(MembershipMetricsWidget::class)
        ->assertSee(__('app.widgets.active_members'))
        ->assertSee(__('app.widgets.vs_previous_period', ['count' => 0]))
        ->assertDontSee(__('app.status.expiring'));
});
