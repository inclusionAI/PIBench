<?php

namespace App\Support\Billing;

/**
 * Payment method normalization + display helpers.
 *
 * The app stores payment method values as strings on invoices/transactions.
 * For dashboards and tables, we intentionally group them as:
 * - Online (gateway / link based)
 * - Offline (cash / UPI / cheque, etc.)
 *
 * This keeps UI consistent while still allowing the raw stored value to evolve.
 */
final class PaymentMethod
{
    /**
     * Normalize a raw payment method value to a canonical string.
     */
    public static function normalize(?string $value): string
    {
        $value = strtolower(trim((string) $value));

        return $value;
    }

    /**
     * Determine whether a stored payment method represents an online payment flow.
     */
    public static function isOnline(?string $value): bool
    {
        $value = self::normalize($value);

        return in_array($value, ['online', 'stripe'], true);
    }

    /**
     * Human-friendly channel label for a stored payment method value.
     */
    public static function channelLabel(?string $value): string
    {
        return self::isOnline($value)
            ? __('app.payment_methods.online')
            : __('app.payment_methods.offline');
    }

    /**
     * Default Filament options for selecting a payment method.
     *
     * @return array<string, string>
     */
    public static function options(): array
    {
        return [
            'cash' => __('app.payment_methods.offline'),
            'online' => __('app.payment_methods.online'),
            'cheque' => __('app.payment_methods.cheque_legacy'),
        ];
    }
}
