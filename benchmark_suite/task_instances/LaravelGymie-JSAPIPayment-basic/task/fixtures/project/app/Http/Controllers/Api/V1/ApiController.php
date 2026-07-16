<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Controllers\Controller;
use App\Models\User;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Database\Eloquent\SoftDeletingScope;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * Base API controller helpers for v1 endpoints.
 */
abstract class ApiController extends Controller
{
    /**
     * Abort with 403 unless the current user has the given permission.
     */
    protected function requirePermission(Request $request, string $permission): void
    {
        abort_unless($request->user()?->can($permission) === true, 403);
    }

    /**
     * Return a 204 No Content JSON response.
     */
    protected function noContent(): JsonResponse
    {
        return response()->json([], 204);
    }

    /**
     * Delete a model and return a 204 No Content response.
     */
    protected function deleteModel(Request $request, string $permission, Model $record): JsonResponse
    {
        $this->requirePermission($request, $permission);

        $record->delete();

        return $this->noContent();
    }

    /**
     * Return the authenticated API user or abort with 401.
     */
    protected function currentUser(Request $request): User
    {
        $user = $request->user();
        abort_unless($user instanceof User, 401);

        return $user;
    }

    /**
     * Restore a soft-deleted record for a given model class.
     *
     * @template TModel of \Illuminate\Database\Eloquent\Model
     *
     * @param  class-string<TModel>  $modelClass
     * @return TModel
     */
    protected function restoreSoftDeleted(Request $request, string $permission, string $modelClass, int $id): Model
    {
        $this->requirePermission($request, $permission);

        abort_unless(in_array(SoftDeletes::class, class_uses_recursive($modelClass), true), 404);

        /** @var TModel $record */
        $record = $this->softDeletedQuery($modelClass)->findOrFail($id);

        if (method_exists($record, 'restore')) {
            $record->restore();
        }

        return $record;
    }

    /**
     * Permanently delete a soft-deleted record for a given model class.
     *
     * @param  class-string<\Illuminate\Database\Eloquent\Model>  $modelClass
     */
    protected function forceDeleteSoftDeleted(Request $request, string $permission, string $modelClass, int $id): void
    {
        $this->requirePermission($request, $permission);

        abort_unless(in_array(SoftDeletes::class, class_uses_recursive($modelClass), true), 404);

        $record = $this->softDeletedQuery($modelClass)->findOrFail($id);
        $record->forceDelete();
    }

    /**
     * Create a query that includes soft-deleted records for the given model class.
     *
     * @template TModel of \Illuminate\Database\Eloquent\Model
     *
     * @param  class-string<TModel>  $modelClass
     * @return Builder<TModel>
     */
    private function softDeletedQuery(string $modelClass): Builder
    {
        /** @var Builder<TModel> $query */
        $query = $modelClass::query()->withoutGlobalScope(SoftDeletingScope::class);

        return $query;
    }
}
