<?php

namespace App\Http\Resources\V1;

use App\Services\Api\Schemas\FollowUpSchema;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \App\Models\FollowUp
 */
class FollowUpResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        /** @var \App\Models\FollowUp $followUp */
        $followUp = $this->resource;

        return FollowUpSchema::resource($followUp);
    }
}
