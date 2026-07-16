<?php

namespace App\Http\Requests\Api\V1;

use App\Services\Api\Schemas\MemberSchema;
use Illuminate\Foundation\Http\FormRequest;

/**
 * Create member request.
 */
class MemberStoreRequest extends FormRequest
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
        return MemberSchema::storeRules();
    }
}
