<?php

use App\Helpers\Helpers;
use App\Mail\InvoiceIssuedMail;
use App\Models\Invoice;
use App\Models\Member;
use App\Models\Plan;
use App\Models\Subscription;
use App\Services\Email\InvoiceEmailService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Mail;

uses(RefreshDatabase::class);

afterEach(function (): void {
    Helpers::setTestSettingsOverride(null);
});

it('sends invoice issued email with reply-to when gym email is configured', function (): void {
    Helpers::setTestSettingsOverride([
        'general' => [
            'gym_name' => 'Demo Gym',
            'gym_email' => 'gym@example.com',
            'gym_contact' => '9999999999',
            'currency' => 'INR',
        ],
        'charges' => [
            'taxes' => 0,
            'discounts' => [],
        ],
    ]);

    Mail::fake();

    $member = Member::factory()->create([
        'name' => 'Test Member',
        'email' => 'member@example.com',
    ]);

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

    app(InvoiceEmailService::class)->sendInvoiceIssuedEmail(
        invoiceId: $invoice->id,
        toEmail: $member->email,
        note: 'Hello',
    );

    Mail::assertSent(InvoiceIssuedMail::class, function (InvoiceIssuedMail $mail) use ($invoice): bool {
        return $mail->invoice->is($invoice)
            && $mail->hasReplyTo('gym@example.com')
            && count($mail->attachments()) === 1;
    });
});
