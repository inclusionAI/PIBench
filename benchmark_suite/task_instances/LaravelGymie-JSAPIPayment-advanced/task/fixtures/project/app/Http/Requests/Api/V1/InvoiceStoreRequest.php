<?php

namespace App\Http\Requests\Api\V1;

use App\Services\Api\Schemas\InvoiceSchema;
use Illuminate\Foundation\Http\FormRequest;

/**
 * Create invoice request.
 */
class InvoiceStoreRequest extends FormRequest
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
        return InvoiceSchema::storeRules();
    }
}
