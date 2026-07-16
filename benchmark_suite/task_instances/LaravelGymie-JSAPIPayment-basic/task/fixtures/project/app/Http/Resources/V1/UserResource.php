<?php

namespace App\Http\Resources\V1;

use App\Services\Api\Schemas\UserSchema;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\JsonResource;

/**
 * @mixin \App\Models\User
 */
class UserResource extends JsonResource
{
    private function shouldIncludePermissions(Request $request): bool
    {
        if ($request->is('api/v1/me')) {
            return true;
        }

        $include = (string) $request->query('include', '');

        return in_array('permissions', array_filter(explode(',', $include)), true)
            || $request->boolean('include_permissions');
    }

    /**
     * Transform the resource into an array.
     *
     * @return array<string, mixed>
     */
    public function toArray(Request $request): array
    {
        /** @var \App\Models\User $user */
        $user = $this->resource;

        return UserSchema::resource($user, $this->shouldIncludePermissions($request));
    }
}
