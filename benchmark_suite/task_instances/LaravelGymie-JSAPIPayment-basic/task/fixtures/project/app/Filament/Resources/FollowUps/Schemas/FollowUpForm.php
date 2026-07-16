<?php

namespace App\Filament\Resources\FollowUps\Schemas;

use App\Filament\Resources\Enquiries\RelationManagers\FollowUpsRelationManager;
use Filament\Forms\Components\DatePicker;
use Filament\Forms\Components\Select;
use Filament\Schemas\Schema;

class FollowUpForm
{
    /**
     * Configure the follow-up form schema.
     */
    public static function configure(Schema $schema): Schema
    {
        return $schema
            ->columns(1)
            ->components([
                Select::make('enquiry_id')
                    ->label(__('app.resources.enquiries.singular'))
                    ->relationship(name: 'enquiry', titleAttribute: 'name')
                    ->placeholder(__('app.placeholders.select_enquiry'))
                    ->hiddenOn(FollowUpsRelationManager::class)
                    ->required(),
                Select::make('method')
                    ->options([
                        'call' => __('app.options.follow_up_method.call'),
                        'email' => __('app.options.follow_up_method.email'),
                        'in_person' => __('app.options.follow_up_method.in_person'),
                        'whatsapp' => __('app.options.follow_up_method.whatsapp'),
                        'other' => __('app.options.follow_up_method.other'),
                    ])->default('call')
                    ->required()
                    ->label(__('app.fields.method')),
                DatePicker::make('schedule_date')
                    ->label(__('app.fields.schedule_date'))
                    ->closeOnDateSelection()
                    ->required()
                    ->required()
                    ->minDate(now()),
            ]);
    }
}
