<?php

namespace App\Services\Api\Schemas;

use App\Models\Service;

/**
 * Single source of truth for Service API validation and serialization.
 */
final class ServiceSchema
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
            'searchable' => ['name', 'description'],
            'sortable' => ['id', 'created_at', 'name'],
            'default_sort' => '-id',
            'status_column' => null,
            'includes' => [],
            'filters' => [
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
            'description' => ['nullable', 'string'],
        ];
    }

    /**
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public static function updateRules(): array
    {
        return [
            'name' => ['sometimes', 'string', 'max:255'],
            'description' => ['sometimes', 'nullable', 'string'],
        ];
    }

    /**
     * @return array<string, mixed>
     */
    public static function resource(Service $service): array
    {
        return [
            'id' => (int) $service->id,
            'name' => (string) $service->name,
            'description' => $service->description ? (string) $service->description : null,
            'created_at' => $service->created_at?->toISOString(),
            'updated_at' => $service->updated_at?->toISOString(),
            'deleted_at' => $service->deleted_at?->toISOString(),
        ];
    }
}
