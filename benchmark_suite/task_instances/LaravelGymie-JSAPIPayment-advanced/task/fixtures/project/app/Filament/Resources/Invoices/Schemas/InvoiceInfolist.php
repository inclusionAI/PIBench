<?php

namespace App\Filament\Resources\Invoices\Schemas;

use App\Helpers\Helpers;
use App\Models\Invoice;
use App\Support\Billing\PaymentMethod;
use Filament\Infolists\Components\TextEntry;
use Filament\Schemas\Components\Flex;
use Filament\Schemas\Components\Grid;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;
use Filament\Support\Enums\FontWeight;
use Illuminate\Support\Facades\Blade;
use Illuminate\Support\HtmlString;

class InvoiceInfolist
{
    /**
     * Configure the invoice "view" infolist schema.
     */
    public static function configure(Schema $schema): Schema
    {
        return $schema
            ->columns(1)
            ->components([
                Grid::make(4)
                    ->schema([
                        Section::make()
                            ->heading(function (Invoice $record): HtmlString {
                                $status = $record->status;

                                if ($status === null) {
                                    return new HtmlString(e(__('app.ui.details')));
                                }

                                $html = Blade::render(
                                    '<x-filament::badge class="inline-flex ml-2" :color="$color">
                                        {{ $label }}
                                    </x-filament::badge>',
                                    [
                                        'color' => $status->getColor(),
                                        'label' => $status->getLabel(),
                                    ]
                                );

                                return new HtmlString(e(__('app.ui.details')).' '.$html);
                            })
                            ->schema([
                                TextEntry::make('number')->label(__('app.fields.invoice_number')),
                                TextEntry::make('subscription.member')
                                    ->label(__('app.fields.subscription'))
                                    ->weight(FontWeight::Bold)
                                    ->color('success')
                                    ->formatStateUsing(fn ($record): string => "{$record->subscription->member->code} – {$record->subscription->member->name}")
                                    ->url(fn ($record): string => route('filament.admin.resources.subscriptions.view', $record->subscription_id)),
                                TextEntry::make('date')->label(__('app.fields.date'))->date(),
                                TextEntry::make('due_date')
                                    ->label(__('app.fields.due_date'))
                                    ->date(),
                                TextEntry::make('payment_method')
                                    ->label(__('app.fields.payment_method'))
                                    ->formatStateUsing(fn (?string $state): string => $state ? PaymentMethod::channelLabel($state) : __('app.placeholders.dash')),
                                TextEntry::make('discount_note')
                                    ->label(__('app.fields.discount_note'))
                                    ->placeholder(__('app.placeholders.na')),
                            ])
                            ->columns(3)
                            ->columnSpan(3),

                        Section::make(__('app.titles.summary'))
                            ->schema([
                                Flex::make([
                                    TextEntry::make('fee_label')
                                        ->label(__('app.fields.fee').':'),
                                    TextEntry::make('subscription_fee')
                                        ->hiddenLabel()
                                        ->formatStateUsing(fn (Invoice $record) => Helpers::formatCurrency($record->subscription_fee)),
                                ]),
                                Flex::make([
                                    TextEntry::make('tax_label')
                                        ->label(__('app.fields.tax_with_rate', ['rate' => Helpers::getTaxRate()]).':'),
                                    TextEntry::make('tax')
                                        ->hiddenLabel()
                                        ->formatStateUsing(fn (Invoice $record) => Helpers::formatCurrency($record->tax)),
                                ])->hidden(fn ($record) => empty($record->tax)),
                                Flex::make([
                                    TextEntry::make('discount_label')
                                        ->label(fn (Invoice $record) => $record->discount
                                            ? __('app.fields.discount_with_rate', ['rate' => $record->discount]).':'
                                            : __('app.fields.discount').':'),
                                    TextEntry::make('discount_amount')
                                        ->hiddenLabel()
                                        ->formatStateUsing(fn (Invoice $record) => Helpers::formatCurrency($record->discount_amount)),
                                ])->hidden(fn ($record) => empty($record->discount_amount)),
                                Flex::make([
                                    TextEntry::make('total_label')
                                        ->label(__('app.fields.total').':'),
                                    TextEntry::make('total_amount')
                                        ->hiddenLabel()
                                        ->formatStateUsing(fn (Invoice $record) => Helpers::formatCurrency($record->total_amount)),
                                ]),
                                Flex::make([
                                    TextEntry::make('paid_label')
                                        ->label(__('app.fields.paid').':'),
                                    TextEntry::make('paid_amount')
                                        ->hiddenLabel()
                                        ->formatStateUsing(fn (Invoice $record) => Helpers::formatCurrency($record->paid_amount)),
                                ])->hidden(fn ($record) => empty($record->paid_amount)),
                                Flex::make([
                                    TextEntry::make('due_label')
                                        ->label(__('app.fields.due').':'),
                                    TextEntry::make('due_amount')
                                        ->hiddenLabel()
                                        ->formatStateUsing(fn (Invoice $record) => Helpers::formatCurrency($record->due_amount)),
                                ])->hidden(fn ($record) => empty($record->due_amount)),

                            ])
                            ->columns(1)
                            ->columnSpan(1),
                    ]),
            ]);
    }
}
