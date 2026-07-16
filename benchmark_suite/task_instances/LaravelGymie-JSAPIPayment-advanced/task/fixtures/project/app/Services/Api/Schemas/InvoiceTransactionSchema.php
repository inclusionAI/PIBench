<?php

namespace App\Services\Api\Schemas;

use App\Models\InvoiceTransaction;
use Illuminate\Validation\Rule;

/**
 * Single source of truth for InvoiceTransaction API validation and serialization.
 */
final class InvoiceTransactionSchema
{
    private function __construct() {}

    /**
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public static function storeRules(): array
    {
        return [
            'type' => ['required', 'string', Rule::in(['payment', 'refund'])],
            'amount' => ['required', 'numeric', 'min:0.01'],
            'occurred_at' => ['nullable', 'date'],
            'payment_method' => ['nullable', 'string', 'max:50'],
            'note' => ['nullable', 'string'],
            'reference_id' => ['nullable', 'string', 'max:255'],
        ];
    }

    /**
     * @return array<string, mixed>
     */
    public static function resource(InvoiceTransaction $transaction): array
    {
        return [
            'id' => (int) $transaction->id,
            'invoice_id' => (int) $transaction->invoice_id,
            'type' => (string) $transaction->type,
            'amount' => (float) ($transaction->amount ?? 0),
            'occurred_at' => $transaction->occurred_at?->toISOString(),
            'payment_method' => $transaction->payment_method ? (string) $transaction->payment_method : null,
            'note' => $transaction->note ? (string) $transaction->note : null,
            'reference_id' => $transaction->reference_id ? (string) $transaction->reference_id : null,
            'created_by' => $transaction->created_by ? (int) $transaction->created_by : null,
            'created_at' => $transaction->created_at?->toISOString(),
            'updated_at' => $transaction->updated_at?->toISOString(),
        ];
    }
}
