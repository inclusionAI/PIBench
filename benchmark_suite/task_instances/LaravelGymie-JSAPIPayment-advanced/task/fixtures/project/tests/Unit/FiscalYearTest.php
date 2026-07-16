<?php

use App\Support\Dates\FiscalYear;
use Carbon\CarbonImmutable;

it('calculates fiscal year span for dates after the start', function (): void {
    [$start, $end] = FiscalYear::spanForDate(
        CarbonImmutable::parse('2026-05-01'),
        [
            'financial_year_start' => '2026-04-01',
            'financial_year_end' => '2027-03-31',
        ],
    );

    expect($start->toDateString())->toBe('2026-04-01');
    expect($end->toDateString())->toBe('2027-03-31');
});

it('shifts fiscal year back when date is before the start', function (): void {
    [$start, $end] = FiscalYear::spanForDate(
        CarbonImmutable::parse('2026-02-01'),
        [
            'financial_year_start' => '2026-04-01',
            'financial_year_end' => '2027-03-31',
        ],
    );

    expect($start->toDateString())->toBe('2025-04-01');
    expect($end->toDateString())->toBe('2026-03-31');
});
