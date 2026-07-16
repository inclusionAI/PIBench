<?php

namespace App\Http\Resources\V1;

use App\Services\Api\Schemas\EnquirySchema;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \App\Models\Enquiry
 */
class EnquiryResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        /** @var \App\Models\Enquiry $enquiry */
        $enquiry = $this->resource;

        return EnquirySchema::resource($enquiry);
    }
}
