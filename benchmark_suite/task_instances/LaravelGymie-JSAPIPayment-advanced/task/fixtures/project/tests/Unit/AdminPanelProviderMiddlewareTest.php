<?php

use App\Http\Middleware\SetAppLocale;
use App\Providers\Filament\AdminPanelProvider;
use Filament\Panel;

it('includes the locale middleware in the admin panel stack', function (): void {
    $provider = new AdminPanelProvider(app());

    $panel = $provider->basePanel(Panel::make());

    expect($panel->getMiddleware())->toContain(SetAppLocale::class);
});
