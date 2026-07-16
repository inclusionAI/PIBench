<?php

namespace App\Support\Billing;

/**
 * Invoice math helper used by Filament forms.
 *
 * This calculator intentionally matches the current UI behavior:
 * - Values are rounded to whole currency units for on-screen summaries.
 * - Discount amount is clamped to the fee (cannot exceed it).
 * - Paid amount is clamped to the computed total.
 *
 * The `Invoice` model remains the source of truth for persisted totals.
 */
final class InvoiceCalculator
{
    /**
     * Calculate summary values (fee/tax/total/paid/due) for a single invoice.
     *
     * @return array{
     *   fee: float,
     *   tax: float,
     *   discount_amount: float,
     *   total: float,
     *   paid: float,
     *   due: float,
     * }
     */
    public static function summary(
        float $fee,
        float $taxRatePercent,
        float $discountAmount,
        float $paidAmount,
    ): array {
        $fee = max(round($fee), 0.0);
        $taxRatePercent = max($taxRatePercent, 0.0);

        $tax = round(($fee * $taxRatePercent) / 100);

        $discountAmount = min(max($discountAmount, 0.0), $fee);
        $discountAmount = round($discountAmount);

        $total = round(max($fee + $tax - $discountAmount, 0.0));

        $paidAmount = min(max($paidAmount, 0.0), $total);
        $paidAmount = round($paidAmount);

        $due = round(max($total - $paidAmount, 0.0));

        return [
            'fee' => (float) $fee,
            'tax' => (float) $tax,
            'discount_amount' => (float) $discountAmount,
            'total' => (float) $total,
            'paid' => (float) $paidAmount,
            'due' => (float) $due,
        ];
    }
}
