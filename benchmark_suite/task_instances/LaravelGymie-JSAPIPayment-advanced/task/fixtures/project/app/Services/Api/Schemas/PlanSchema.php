<?php

namespace App\Services\Api\Schemas;

use App\Enums\Status;
use App\Models\Plan;
use App\Models\Service;
use App\Rules\ModelExists;
use App\Rules\ModelUnique;

/**
 * Single source of truth for Plan API validation and serialization.
 */
final class PlanSchema
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
            'searchable' => ['name', 'code', 'description'],
            'sortable' => ['id', 'created_at', 'name'],
            'default_sort' => '-id',
            'status_column' => 'status',
            'includes' => ['service'],
            'filters' => [
                'service_id' => ['type' => 'exact', 'column' => 'service_id'],
                'status' => ['type' => 'exact', 'column' => 'status'],
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
            'name' => ['required', 'string', 'max:255', new ModelUnique(Plan::class, 'name')],
            'code' => ['required', 'string', 'max:255', new ModelUnique(Plan::class, 'code')],
            'description' => ['nullable', 'string'],
            'service_id' => ['required', 'integer', new ModelExists(Service::class)],
            'amount' => ['required', 'numeric', 'min:0'],
            'days' => ['required', 'integer', 'min:1'],
            'status' => ['nullable', 'string'],
        ];
    }

    /**
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public static function updateRules(int|string $planId): array
    {
        return [
            'name' => ['sometimes', 'string', 'max:255', new ModelUnique(Plan::class, 'name', $planId)],
            'code' => ['sometimes', 'string', 'max:255', new ModelUnique(Plan::class, 'code', $planId)],
            'description' => ['sometimes', 'nullable', 'string'],
            'service_id' => ['sometimes', 'integer', new ModelExists(Service::class)],
            'amount' => ['sometimes', 'numeric', 'min:0'],
            'days' => ['sometimes', 'integer', 'min:1'],
            'status' => ['sometimes', 'nullable', 'string'],
        ];
    }

    /**
     * @return array<string, mixed>
     */
    public static function resource(Plan $plan): array
    {
        $payload = [
            'id' => (int) $plan->id,
            'name' => (string) $plan->name,
            'code' => $plan->code ? (string) $plan->code : null,
            'description' => $plan->description ? (string) $plan->description : null,
            'amount' => (float) ($plan->amount ?? 0),
            'days' => (int) ($plan->days ?? 0),
            'status' => Status::valueOf($plan->status),
            'created_at' => $plan->created_at?->toISOString(),
            'updated_at' => $plan->updated_at?->toISOString(),
            'deleted_at' => $plan->deleted_at?->toISOString(),
        ];

        if ($plan->relationLoaded('service') && $plan->service) {
            $payload['service'] = [
                'id' => (int) $plan->service->id,
                'name' => (string) $plan->service->name,
            ];
        }

        return $payload;
    }
}
