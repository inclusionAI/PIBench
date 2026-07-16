<?php

namespace App\Support\Billing;

use Illuminate\Support\Number;
use NumberFormatter;

/**
 * Currency helpers for formatting and symbol resolution.
 */
final class Currency
{
    /**
     * Resolve a currency code from settings.
     *
     * @param  array<string, mixed>  $settings
     */
    public static function codeFromSettings(array $settings, string $defaultCode = 'INR'): string
    {
        $currency = $settings['general']['currency'] ?? null;

        return filled($currency) ? (string) $currency : $defaultCode;
    }

    /**
     * Format a currency value using the app's configured formatting.
     */
    public static function format(?float $value, string $currencyCode): string
    {
        return Number::currency($value ?? 0, $currencyCode, null, 0);
    }

    /**
     * Resolve a currency symbol for a currency code.
     */
    public static function symbol(string $currencyCode): string
    {
        $formatter = new NumberFormatter('en'."@currency={$currencyCode}", NumberFormatter::CURRENCY);

        return $formatter->getSymbol(NumberFormatter::CURRENCY_SYMBOL) ?: '';
    }
}
