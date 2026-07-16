<?php

namespace App\Http\Requests\Api\V1;

use App\Services\Api\Schemas\ExpenseSchema;
use Illuminate\Foundation\Http\FormRequest;

/**
 * Create expense request.
 */
class ExpenseStoreRequest extends FormRequest
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
        return ExpenseSchema::storeRules();
    }
}
