<?php

namespace App\Support;

use Stringable;

final class Data
{
    public static function string(mixed $value, string $default = ''): string
    {
        if (is_string($value)) {
            return $value;
        }

        if (is_int($value) || is_float($value) || is_bool($value) || $value instanceof Stringable) {
            return (string) $value;
        }

        return $default;
    }

    public static function nullableString(mixed $value): ?string
    {
        $string = trim(self::string($value));

        return $string !== '' ? $string : null;
    }

    public static function int(mixed $value, int $default = 0): int
    {
        return is_numeric($value) ? (int) $value : $default;
    }

    public static function float(mixed $value, float $default = 0.0): float
    {
        return is_numeric($value) ? (float) $value : $default;
    }

    /**
     * @return array<array-key, mixed>
     */
    public static function array(mixed $value): array
    {
        return is_array($value) ? $value : [];
    }

    /**
     * @return array<string, mixed>
     */
    public static function map(mixed $value): array
    {
        if (! is_array($value)) {
            return [];
        }

        $mapped = [];

        foreach ($value as $key => $item) {
            $mapped[(string) $key] = $item;
        }

        return $mapped;
    }
}
