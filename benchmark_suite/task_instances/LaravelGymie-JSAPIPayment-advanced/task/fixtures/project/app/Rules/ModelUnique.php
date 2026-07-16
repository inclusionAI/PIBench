<?php

namespace App\Rules;

use Closure;
use Illuminate\Contracts\Validation\ValidationRule;
use Illuminate\Database\Eloquent\Model;

/**
 * Eloquent-based "unique" rule (respects global scopes like tenancy / soft deletes).
 *
 * @template TModel of \Illuminate\Database\Eloquent\Model
 */
final class ModelUnique implements ValidationRule
{
    /**
     * @param  class-string<TModel>  $modelClass
     */
    public function __construct(
        private string $modelClass,
        private string $column,
        private int|string|null $ignoreId = null,
    ) {}

    /**
     * @param  Closure(string, string|null=): \Illuminate\Translation\PotentiallyTranslatedString  $fail
     */
    public function validate(string $attribute, mixed $value, Closure $fail): void
    {
        if ($value === null || $value === '') {
            return;
        }

        $modelClass = $this->modelClass;

        /** @var Model $model */
        $model = new $modelClass;

        $query = $modelClass::query()->where($this->column, $value);

        if ($this->ignoreId !== null) {
            $query->where($model->getKeyName(), '!=', $this->ignoreId);
        }

        if ($query->exists()) {
            $fail(__('validation.unique', ['attribute' => $attribute]));
        }
    }
}
