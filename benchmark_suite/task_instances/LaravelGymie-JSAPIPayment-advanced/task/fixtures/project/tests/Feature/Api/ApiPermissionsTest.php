<?php

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Spatie\Permission\Models\Permission;
use Spatie\Permission\PermissionRegistrar;

uses(RefreshDatabase::class);

it('returns an unauthenticated JSON response without redirecting to a login route', function (): void {
    $this->getJson('/api/v1/members')
        ->assertUnauthorized()
        ->assertJsonPath('message', 'Unauthenticated.');
});

it('forbids access when required permissions are missing', function (): void {
    $user = User::factory()->create();

    Sanctum::actingAs($user);

    $this->getJson('/api/v1/members')->assertForbidden();
});

it('allows access when the correct permission is granted', function (): void {
    app(PermissionRegistrar::class)->forgetCachedPermissions();
    Permission::findOrCreate('ViewAny:Member', 'web');

    $user = User::factory()->create();
    $user->givePermissionTo('ViewAny:Member');

    Sanctum::actingAs($user);

    $this->getJson('/api/v1/members')->assertSuccessful();
});
