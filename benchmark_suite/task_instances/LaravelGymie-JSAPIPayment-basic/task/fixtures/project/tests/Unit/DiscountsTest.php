<?php

use App\Support\Billing\Discounts;

it('builds discount options from settings', function (): void {
    $options = Discounts::optionsFromSettings([
        'charges' => [
            'discounts' => [10, '20'],
        ],
    ]);

    expect($options)->toHaveKeys(['10', '20']);
});

it('calculates discount amount', function (): void {
    expect(Discounts::amount(10, 1000))->toBe(100.0);
    expect(Discounts::amount(null, 1000))->toBe(0.0);
    expect(Discounts::amount(10, null))->toBe(0.0);
});
