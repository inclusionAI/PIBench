<?php

namespace App\Filament\Resources\Services;

use App\Filament\Resources\Services\Pages\ListServices;
use App\Filament\Resources\Services\Schemas\ServiceForm;
use App\Filament\Resources\Services\Schemas\ServiceInfolist;
use App\Filament\Resources\Services\Tables\ServiceTable;
use App\Models\Service;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Model;

class ServiceResource extends Resource
{
    protected static ?string $model = Service::class;

    protected static ?string $recordTitleAttribute = 'name';

    public static function getModelLabel(): string
    {
        return __('app.resources.services.singular');
    }

    public static function getPluralModelLabel(): string
    {
        return __('app.resources.services.plural');
    }

    public static function getNavigationLabel(): string
    {
        return static::getPluralModelLabel();
    }

    public static function getGloballySearchableAttributes(): array
    {
        return [
            'name',
            'description',
        ];
    }

    public static function getGlobalSearchResultDetails(Model $record): array
    {
        /** @var Service $record */
        if (blank($record->description)) {
            return [];
        }

        return [
            __('app.fields.description') => $record->description,
        ];
    }

    public static function form(Schema $schema): Schema
    {
        return ServiceForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return ServiceTable::configure($table);
    }

    /**
     * Add infolist to the resource.
     */
    public static function infolist(Schema $schema): Schema
    {
        return ServiceInfolist::configure($schema);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListServices::route('/'),
        ];
    }
}
