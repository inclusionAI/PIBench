<?php

namespace App\Services\Api\Schemas;

use Spatie\Permission\Models\Role;

/**
 * Single source of truth for Role API serialization.
 */
final class RoleSchema
{
    private function __construct() {}

    /**
     * @return array<string, mixed>
     */
    public static function resource(Role $role): array
    {
        return [
            'id' => (int) $role->id,
            'name' => (string) $role->name,
            'guard_name' => (string) $role->guard_name,
            'permissions' => $role->permissions->pluck('name')->values()->all(),
        ];
    }
}
