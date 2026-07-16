<?php

use App\Filament\Resources\FollowUps\Tables\FollowUpTable;
use Filament\Tables\Columns\Column;

it('exposes reusable follow-up table columns', function (): void {
    $columns = FollowUpTable::getColumns();

    expect($columns)->toBeArray();
    expect($columns)->not->toBeEmpty();
    expect($columns)->each->toBeInstanceOf(Column::class);
});

it('exposes reusable follow-up filters and actions', function (): void {
    expect(FollowUpTable::getTableFilters())->toBeArray();
    expect(FollowUpTable::getTableActions())->toBeArray();
});
