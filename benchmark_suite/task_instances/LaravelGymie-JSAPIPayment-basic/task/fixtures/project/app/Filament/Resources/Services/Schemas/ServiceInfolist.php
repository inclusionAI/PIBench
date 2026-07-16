<?php

namespace App\Filament\Resources\Services\Schemas;

use Filament\Infolists\Components\TextEntry;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

class ServiceInfolist
{
    /**
     * Configure the service "view" infolist schema.
     */
    public static function configure(Schema $schema): Schema
    {
        return $schema
            ->columns(1)
            ->components([
                Section::make('')
                    ->schema([
                        TextEntry::make('name')
                            ->label(__('app.fields.name')),
                        TextEntry::make('description')
                            ->label(__('app.fields.description')),
                    ])->columns(1),
            ]);
    }
}
