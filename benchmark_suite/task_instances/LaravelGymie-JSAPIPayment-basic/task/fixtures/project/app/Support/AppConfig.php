<?php

namespace App\Support;

final class AppConfig
{
    public static function string(string $key, string $default = ''): string
    {
        $value = config($key);

        return is_string($value) && $value !== '' ? $value : $default;
    }

    public static function timezone(): string
    {
        return self::string('app.timezone', 'UTC');
    }

    /**
     * @return list<string>
     */
    public static function supportedLocales(): array
    {
        $locales = config('app.supported_locales', []);

        if (! is_array($locales) || $locales === []) {
            return [self::string('app.locale', 'en')];
        }

        $values = [];

        foreach ($locales as $locale) {
            if (! is_scalar($locale)) {
                continue;
            }

            $value = trim((string) $locale);

            if ($value === '') {
                continue;
            }

            $values[] = $value;
        }

        return $values !== [] ? $values : [self::string('app.locale', 'en')];
    }
}
