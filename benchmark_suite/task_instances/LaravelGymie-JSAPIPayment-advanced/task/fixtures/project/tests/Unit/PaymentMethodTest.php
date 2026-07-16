<?php

use App\Support\Billing\PaymentMethod;

it('normalizes and classifies payment methods', function (): void {
    expect(PaymentMethod::normalize(' Stripe '))->toBe('stripe');
    expect(PaymentMethod::isOnline('stripe'))->toBeTrue();
    expect(PaymentMethod::isOnline('online'))->toBeTrue();
    expect(PaymentMethod::isOnline('cash'))->toBeFalse();
    expect(PaymentMethod::channelLabel('stripe'))->toBe(__('app.payment_methods.online'));
    expect(PaymentMethod::channelLabel('cash'))->toBe(__('app.payment_methods.offline'));
});

it('exposes stable payment method options for forms', function (): void {
    expect(PaymentMethod::options())->toMatchArray([
        'cash' => __('app.payment_methods.offline'),
        'online' => __('app.payment_methods.online'),
        'cheque' => __('app.payment_methods.cheque_legacy'),
    ]);
});
