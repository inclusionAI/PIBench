<?php

namespace App\Http\Requests\Api\V1;

use App\Services\Api\Schemas\InvoiceTransactionSchema;
use Illuminate\Foundation\Http\FormRequest;

/**
 * Create invoice transaction request.
 */
class InvoiceTransactionStoreRequest extends FormRequest
{
    /**
     * Determine if the user is authorized to make this request.
     */
    public function authorize(): bool
    {
        return true;
    }

    /**
     * Get the validation rules that apply to the request.
     *
     * @return array<string, \Illuminate\Contracts\Validation\ValidationRule|array<mixed>|string>
     */
    public function rules(): array
    {
        return InvoiceTransactionSchema::storeRules();
    }
}
