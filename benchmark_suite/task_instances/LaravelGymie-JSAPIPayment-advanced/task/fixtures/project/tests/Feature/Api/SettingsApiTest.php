<?php

use App\Helpers\Helpers;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Laravel\Sanctum\Sanctum;

uses(RefreshDatabase::class);

afterEach(function (): void {
    Helpers::setTestSettingsOverride(null);
});

it('reads and updates settings via the API', function (): void {
    $user = User::factory()->create();

    Sanctum::actingAs($user);

    $this->getJson('/api/v1/settings')
        ->assertSuccessful()
        ->assertJsonStructure(['data']);

    $response = $this->putJson('/api/v1/settings', [
        'general' => [
            'gym_name' => 'Demo Gym',
        ],
    ])->assertSuccessful();

    expect((string) $response->json('data.general.gym_name'))->toBe('Demo Gym');
});
