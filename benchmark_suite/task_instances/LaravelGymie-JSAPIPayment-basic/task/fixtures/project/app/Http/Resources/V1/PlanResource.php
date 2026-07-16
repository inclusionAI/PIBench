<?php

namespace App\Http\Resources\V1;

use App\Services\Api\Schemas\PlanSchema;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \App\Models\Plan
 */
class PlanResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        /** @var \App\Models\Plan $plan */
        $plan = $this->resource;

        return PlanSchema::resource($plan);
    }
}
