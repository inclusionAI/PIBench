<?php

namespace App\Http\Resources\V1;

use App\Services\Api\Schemas\InvoiceTransactionSchema;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \App\Models\InvoiceTransaction
 */
class InvoiceTransactionResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        /** @var \App\Models\InvoiceTransaction $transaction */
        $transaction = $this->resource;

        return InvoiceTransactionSchema::resource($transaction);
    }
}
