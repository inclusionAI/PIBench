<?php

namespace App\Services\Api\Schemas;

use Spatie\Permission\Models\Permission;

/**
 * Single source of truth for Permission API serialization.
 */
final class PermissionSchema
{
    private function __construct() {}

    /**
     * @return array<string, mixed>
     */
    public static function resource(Permission $permission): array
    {
        return [
            'id' => (int) $permission->id,
            'name' => (string) $permission->name,
            'guard_name' => (string) $permission->guard_name,
        ];
    }
}
