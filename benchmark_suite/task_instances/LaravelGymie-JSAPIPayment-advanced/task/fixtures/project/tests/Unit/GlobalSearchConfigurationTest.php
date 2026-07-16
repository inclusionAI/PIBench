<?php

use App\Enums\Status;
use App\Filament\Resources\Enquiries\EnquiryResource;
use App\Filament\Resources\Expenses\ExpenseResource;
use App\Filament\Resources\FollowUps\FollowUpResource;
use App\Filament\Resources\Invoices\InvoiceResource;
use App\Filament\Resources\Members\MemberResource;
use App\Filament\Resources\Plans\PlanResource;
use App\Filament\Resources\Services\ServiceResource;
use App\Filament\Resources\Subscriptions\SubscriptionResource;
use App\Filament\Resources\Users\UserResource;
use App\Models\Enquiry;
use App\Models\Expense;
use App\Models\FollowUp;
use App\Models\Invoice;
use App\Models\Member;
use App\Models\Plan;
use App\Models\Service;
use App\Models\Subscription;
use App\Models\User;

test('resources define meaningful global search attributes', function (): void {
    app()->setLocale('en');

    expect(MemberResource::getGloballySearchableAttributes())
        ->toContain('name', 'code', 'email', 'contact');

    expect(EnquiryResource::getGloballySearchableAttributes())
        ->toContain('name', 'email', 'contact');

    expect(InvoiceResource::getGloballySearchableAttributes())
        ->toContain('number', 'subscription.member.name', 'subscription.plan.name');

    expect(SubscriptionResource::getGloballySearchableAttributes())
        ->toContain('member.name', 'member.code', 'plan.name', 'plan.code');

    expect(PlanResource::getGloballySearchableAttributes())
        ->toContain('name', 'code', 'service.name');

    expect(ServiceResource::getGloballySearchableAttributes())
        ->toContain('name', 'description');

    expect(ExpenseResource::getGloballySearchableAttributes())
        ->toContain('name', 'category', 'vendor', 'notes');

    expect(UserResource::getGloballySearchableAttributes())
        ->toContain('name', 'email', 'contact');

    expect(FollowUpResource::getGloballySearchableAttributes())
        ->toContain('enquiry.name', 'user.name', 'method', 'outcome');
});

test('resources provide informative global search titles and details', function (): void {
    app()->setLocale('en');

    $member = new Member([
        'name' => 'John Doe',
        'code' => 'GY-1',
        'email' => 'john@example.com',
        'contact' => '+1 555-0000',
    ]);

    expect((string) MemberResource::getGlobalSearchResultTitle($member))->toBe('John Doe');
    expect(MemberResource::getGlobalSearchResultDetails($member))
        ->toMatchArray([
            __('app.fields.code') => 'GY-1',
            __('app.fields.email') => 'john@example.com',
            __('app.fields.contact') => '+1 555-0000',
        ]);

    $plan = new Plan([
        'name' => 'Gold',
        'code' => 'PL-1',
        'amount' => 99.00,
        'days' => 30,
        'status' => Status::Active,
    ]);

    $service = new Service([
        'name' => 'Membership',
        'description' => 'Gym access',
    ]);

    $plan->setRelation('service', $service);

    $subscription = new Subscription([
        'start_date' => '2026-03-01',
        'end_date' => '2026-03-31',
        'status' => Status::Ongoing,
    ]);
    $subscription->setRelation('member', $member);
    $subscription->setRelation('plan', $plan);

    expect(SubscriptionResource::getGlobalSearchResultTitle($subscription))->toBe('John Doe — Gold');

    $invoice = new Invoice([
        'number' => 'GY-1',
        'date' => '2026-03-01',
        'status' => Status::Issued,
        'total_amount' => 120.50,
    ]);
    $invoice->setRelation('subscription', $subscription);

    expect((string) InvoiceResource::getGlobalSearchResultTitle($invoice))->toBe('GY-1');
    expect(InvoiceResource::getGlobalSearchResultDetails($invoice))
        ->toHaveKey(__('app.fields.member'))
        ->toHaveKey(__('app.fields.invoice_date'))
        ->toHaveKey(__('app.fields.status'))
        ->toHaveKey(__('app.fields.total_amount'));

    $user = new User([
        'name' => 'Alice',
        'email' => 'alice@example.com',
        'contact' => '+1 555-1111',
        'status' => Status::Active,
    ]);

    $enquiry = new Enquiry([
        'name' => 'Jane Prospect',
        'contact' => '+1 555-2222',
        'start_by' => '2026-03-20',
    ]);
    $enquiry->setRelation('user', $user);

    expect((string) EnquiryResource::getGlobalSearchResultTitle($enquiry))->toBe('Jane Prospect');
    expect(EnquiryResource::getGlobalSearchResultDetails($enquiry))
        ->toHaveKey(__('app.fields.contact'))
        ->toHaveKey(__('app.fields.start_by'))
        ->toHaveKey(__('app.fields.handled_by'));

    $followUp = new FollowUp([
        'schedule_date' => '2026-03-22',
        'method' => 'call',
        'status' => Status::Pending,
    ]);
    $followUp->setRelation('enquiry', $enquiry);
    $followUp->setRelation('user', $user);

    expect(FollowUpResource::getGlobalSearchResultTitle($followUp))->toBe('Jane Prospect');
    expect(FollowUpResource::getGlobalSearchResultDetails($followUp))
        ->toHaveKey(__('app.fields.schedule_date'))
        ->toHaveKey(__('app.fields.handled_by'))
        ->toHaveKey(__('app.fields.method'))
        ->toHaveKey(__('app.fields.status'));

    $expense = new Expense([
        'name' => 'Electricity bill',
        'amount' => 50.75,
        'date' => '2026-03-10',
        'status' => Status::Pending,
    ]);

    expect((string) ExpenseResource::getGlobalSearchResultTitle($expense))->toBe('Electricity bill');
    expect(ExpenseResource::getGlobalSearchResultDetails($expense))
        ->toHaveKey(__('app.fields.date'))
        ->toHaveKey(__('app.fields.status'))
        ->toHaveKey(__('app.fields.amount'));

    expect((string) UserResource::getGlobalSearchResultTitle($user))->toBe('Alice');
    expect(UserResource::getGlobalSearchResultDetails($user))
        ->toHaveKey(__('app.fields.email'))
        ->toHaveKey(__('app.fields.contact'))
        ->toHaveKey(__('app.fields.status'));
});
