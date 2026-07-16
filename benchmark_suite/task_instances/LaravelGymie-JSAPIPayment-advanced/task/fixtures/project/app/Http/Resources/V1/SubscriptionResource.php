<?php

namespace App\Http\Resources\V1;

use App\Services\Api\Schemas\SubscriptionSchema;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \App\Models\Subscription
 */
class SubscriptionResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        /** @var \App\Models\Subscription $subscription */
        $subscription = $this->resource;

        return SubscriptionSchema::resource($subscription);
    }
}
