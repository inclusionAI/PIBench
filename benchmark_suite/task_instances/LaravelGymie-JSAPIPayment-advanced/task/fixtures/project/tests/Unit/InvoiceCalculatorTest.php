<?php

use App\Support\Billing\InvoiceCalculator;

it('calculates an invoice summary with rounding and clamping', function (): void {
    $summary = InvoiceCalculator::summary(
        fee: 1000.4,
        taxRatePercent: 10,
        discountAmount: 1500,
        paidAmount: 200,
    );

    expect($summary)->toMatchArray([
        'fee' => 1000.0,
        'tax' => 100.0,
        'discount_amount' => 1000.0,
        'total' => 100.0,
        'paid' => 100.0,
        'due' => 0.0,
    ]);
});

it('never returns negative totals or dues', function (): void {
    $summary = InvoiceCalculator::summary(
        fee: -100,
        taxRatePercent: -10,
        discountAmount: -50,
        paidAmount: -25,
    );

    expect($summary['fee'])->toBe(0.0);
    expect($summary['tax'])->toBe(0.0);
    expect($summary['total'])->toBe(0.0);
    expect($summary['paid'])->toBe(0.0);
    expect($summary['due'])->toBe(0.0);
});
