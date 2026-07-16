<?php

namespace App\Rules;

use Closure;
use Illuminate\Contracts\Validation\ValidationRule;

/**
 * Eloquent-based "exists" rule (respects global scopes like tenancy / soft deletes).
 *
 * @template TModel of \Illuminate\Database\Eloquent\Model
 */
final class ModelExists implements ValidationRule
{
    /**
     * @param  class-string<TModel>  $modelClass
     */
    public function __construct(private string $modelClass) {}

    /**
     * @param  Closure(string, string|null=): \Illuminate\Translation\PotentiallyTranslatedString  $fail
     */
    public function validate(string $attribute, mixed $value, Closure $fail): void
    {
        if ($value === null || $value === '') {
            return;
        }

        if (! is_scalar($value)) {
            $fail(__('validation.exists', ['attribute' => $attribute]));

            return;
        }

        $modelClass = $this->modelClass;

        $exists = $modelClass::query()
            ->whereKey($value)
            ->exists();

        if (! $exists) {
            $fail(__('validation.exists', ['attribute' => $attribute]));
        }
    }
}
