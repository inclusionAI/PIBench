<?php

namespace App\Http\Resources\V1;

use App\Services\Api\Schemas\InvoiceSchema;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \App\Models\Invoice
 */
class InvoiceResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        /** @var \App\Models\Invoice $invoice */
        $invoice = $this->resource;

        return InvoiceSchema::resource($invoice);
    }
}
