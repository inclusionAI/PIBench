<?php

namespace App\Filament\Resources\Expenses\Schemas;

use App\Helpers\Helpers;
use App\Models\Expense;
use Filament\Infolists\Components\TextEntry;
use Filament\Schemas\Components\Fieldset;
use Filament\Schemas\Schema;
use Illuminate\Support\Facades\Blade;
use Illuminate\Support\HtmlString;

class ExpenseInfolist
{
    public static function configure(Schema $schema): Schema
    {
        return $schema
            ->columns(1)
            ->components([
                Fieldset::make(__('app.titles.expense_details'))
                    ->label(function (Expense $record): HtmlString {
                        $status = $record->status;
                        $html = Blade::render(
                            '<x-filament::badge class="inline-flex ml-2" :color="$color">
                                {{ $label }}
                            </x-filament::badge>',
                            [
                                'color' => $status->getColor(),
                                'label' => $status->getLabel(),
                            ]
                        );

                        return new HtmlString($html);
                    })
                    ->schema([
                        TextEntry::make('name')
                            ->label(__('app.fields.expense')),
                        TextEntry::make('category')
                            ->label(__('app.fields.category'))
                            ->formatStateUsing(fn (?string $state): string => Helpers::getExpenseCategoryLabel($state) ?? __('app.placeholders.na')),
                        TextEntry::make('vendor')
                            ->label(__('app.fields.vendor'))
                            ->placeholder(__('app.placeholders.na')),
                        TextEntry::make('amount')
                            ->label(__('app.fields.amount'))
                            ->money(Helpers::getCurrencyCode()),
                        TextEntry::make('date')
                            ->label(__('app.fields.date'))
                            ->date(),
                        TextEntry::make('due_date')
                            ->label(__('app.fields.due_date'))
                            ->date()
                            ->placeholder(__('app.placeholders.na')),
                        TextEntry::make('paid_at')
                            ->label(__('app.fields.paid_at'))
                            ->dateTime()
                            ->placeholder(__('app.placeholders.na')),
                        TextEntry::make('notes')
                            ->label(__('app.fields.note'))
                            ->placeholder(__('app.placeholders.na'))
                            ->columnSpanFull(),
                    ]),
            ]);
    }
}
