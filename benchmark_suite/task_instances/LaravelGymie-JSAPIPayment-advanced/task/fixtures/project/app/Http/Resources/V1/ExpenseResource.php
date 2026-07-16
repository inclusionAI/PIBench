<?php

namespace App\Http\Resources\V1;

use App\Services\Api\Schemas\ExpenseSchema;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \App\Models\Expense
 */
class ExpenseResource extends JsonResource
{
    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        /** @var \App\Models\Expense $expense */
        $expense = $this->resource;

        return ExpenseSchema::resource($expense);
    }
}
