<?php

namespace App\Contracts;

/**
 * Settings persistence abstraction.
 *
 * OSS default uses JSON storage. Other installations can override this binding
 * to store settings elsewhere (for example, in a database).
 */
interface SettingsRepository
{
    /**
     * @return array<string, mixed>
     */
    public function get(): array;

    /**
     * @param  array<string, mixed>  $settings
     */
    public function put(array $settings): void;
}
