<?php

namespace App\Http\Requests\Api\V1;

use Illuminate\Foundation\Http\FormRequest;

/**
 * Update settings JSON payload.
 *
 * This stays permissive (array-shape only) so platform installs can extend
 * settings without changing OSS validation rules.
 */
class SettingsUpdateRequest extends FormRequest
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
        return [
            'general' => ['sometimes', 'array'],
            'invoice' => ['sometimes', 'array'],
            'member' => ['sometimes', 'array'],
            'charges' => ['sometimes', 'array'],
            'expenses' => ['sometimes', 'array'],
            'subscriptions' => ['sometimes', 'array'],
            'payments' => ['sometimes', 'array'],
            'notifications' => ['sometimes', 'array'],
            'notifications.email' => ['sometimes', 'array'],
        ];
    }
}
