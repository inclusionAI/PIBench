<?php

use App\Filament\Pages\Dashboard;

it('does not register quick actions in the dashboard header', function (): void {
    $dashboard = new Dashboard;
    $dashboard->cacheInteractsWithHeaderActions();

    $actions = $dashboard->getCachedHeaderActions();

    expect($actions)->toHaveCount(0);
});

it('does not show an export button in the dashboard header view', function (): void {
    $contents = file_get_contents(resource_path('views/filament/pages/dashboard-header.blade.php'));

    expect($contents)->toBeString()
        ->and($contents)->not->toContain('wire:click="export"');
});
