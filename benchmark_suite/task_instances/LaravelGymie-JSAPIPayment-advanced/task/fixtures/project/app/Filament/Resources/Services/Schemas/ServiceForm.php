<?php

namespace App\Filament\Resources\Services\Schemas;

use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Schema;

class ServiceForm
{
    /**
     * Configure the service form schema.
     */
    public static function configure(Schema $schema): Schema
    {
        return $schema
            ->columns(1)
            ->components([
                TextInput::make('name')
                    ->label(__('app.fields.name'))
                    ->placeholder(__('app.placeholders.service_name'))
                    ->required(),
                Textarea::make('description')
                    ->placeholder(__('app.placeholders.service_description'))
                    ->label(__('app.fields.description'))
                    ->required(),
            ]);
    }
}
