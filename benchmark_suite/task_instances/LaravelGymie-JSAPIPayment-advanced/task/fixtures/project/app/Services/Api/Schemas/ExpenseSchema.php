<?php

namespace App\Services\Api\Schemas;

use App\Models\Expense;

/**
 * Single source of truth for Expense API validation and serialization.
 */
final class ExpenseSchema
{
    private function __construct() {}

    /**
     * @return array{
     *   searchable: list<string>,
     *   sortable: list<string>,
     *   default_sort: string,
     *   status_column: string|null,
     *   includes: list<string>,
     *   filters: array<string, array{type: string, column: string}>
     * }
     */
    public static function queryRules(): array
    {
        return [
            'searchable' => ['name', 'category', 'vendor', 'notes'],
            'sortable' => ['id', 'created_at', 'date', 'amount'],
            'default_sort' => '-id',
            'status_column' => 'status',
            'includes' => [],
            'filters' => [
                'status' => ['type' => 'exact', 'column' => 'status'],
                'category' => ['type' => 'exact', 'column' => 'category'],
                'date' => ['type' => 'date_range', 'column' => 'date'],
                'created_at' => ['type' => 'datetime_range', 'column' => 'created_at'],
            ],
        ];
    }

    /**
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public static function storeRules(): array
    {
        return [
            'name' => ['required', 'string', 'max:255'],
            'amount' => ['required', 'numeric', 'min:0'],
            'date' => ['required', 'date'],
            'due_date' => ['nullable', 'date'],
            'paid_at' => ['nullable', 'date'],
            'category' => ['nullable', 'string', 'max:255'],
            'status' => ['nullable', 'string'],
            'vendor' => ['nullable', 'string', 'max:255'],
            'notes' => ['nullable', 'string'],
        ];
    }

    /**
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public static function updateRules(): array
    {
        return [
            'name' => ['sometimes', 'string', 'max:255'],
            'amount' => ['sometimes', 'numeric', 'min:0'],
            'date' => ['sometimes', 'date'],
            'due_date' => ['sometimes', 'nullable', 'date'],
            'paid_at' => ['sometimes', 'nullable', 'date'],
            'category' => ['sometimes', 'nullable', 'string', 'max:255'],
            'status' => ['sometimes', 'nullable', 'string'],
            'vendor' => ['sometimes', 'nullable', 'string', 'max:255'],
            'notes' => ['sometimes', 'nullable', 'string'],
        ];
    }

    /**
     * @return array<string, mixed>
     */
    public static function resource(Expense $expense): array
    {
        return [
            'id' => (int) $expense->id,
            'name' => (string) $expense->name,
            'amount' => (float) $expense->amount,
            'date' => $expense->date->toDateString(),
            'due_date' => $expense->due_date?->toDateString(),
            'paid_at' => $expense->paid_at?->toISOString(),
            'category' => $expense->category ? (string) $expense->category : null,
            'status' => filled($expense->getRawOriginal('status')) ? $expense->status->value : null,
            'vendor' => $expense->vendor ? (string) $expense->vendor : null,
            'notes' => $expense->notes ? (string) $expense->notes : null,
            'created_at' => $expense->created_at?->toISOString(),
            'updated_at' => $expense->updated_at?->toISOString(),
        ];
    }
}
