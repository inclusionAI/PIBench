<?php

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;
use Spatie\Permission\Models\Permission;
use Spatie\Permission\PermissionRegistrar;

uses(RefreshDatabase::class);

it('localizes API error messages via the locale query parameter', function (): void {
    app(PermissionRegistrar::class)->forgetCachedPermissions();

    $permissions = [
        'ViewAny:Plan',
    ];

    foreach ($permissions as $permission) {
        Permission::findOrCreate($permission, 'web');
    }

    $user = User::factory()->create();
    $user->givePermissionTo($permissions);

    Sanctum::actingAs($user);

    $this->getJson('/api/v1/plans?sort=unknown&locale=fr')
        ->assertStatus(400)
        ->assertJsonPath('message', 'Paramètres de requête invalides.');

    $this->getJson('/api/v1/plans?sort=unknown&locale=ar')
        ->assertStatus(400)
        ->assertJsonPath('message', 'معلمات الاستعلام غير صالحة.');
});
