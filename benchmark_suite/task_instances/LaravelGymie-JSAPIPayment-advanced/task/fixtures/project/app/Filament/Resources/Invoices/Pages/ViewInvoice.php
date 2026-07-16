<?php

namespace App\Filament\Resources\Invoices\Pages;

use App\Filament\Resources\Invoices\InvoiceResource;
use App\Models\Invoice;
use Filament\Actions\EditAction;
use Filament\Resources\Pages\ViewRecord;

/**
 * @property-read Invoice $record
 */
class ViewInvoice extends ViewRecord
{
    protected static string $resource = InvoiceResource::class;

    public function getTitle(): string
    {
        return __('app.titles.invoice_number', ['number' => $this->record->number]);
    }

    protected function getHeaderActions(): array
    {
        return [
            EditAction::make()
                ->hidden(fn (): bool => $this->record->status?->value !== 'issued'),
        ];
    }

    public function getBreadcrumbs(): array
    {
        return [
            __('app.navigation.groups.billing'),
            InvoiceResource::getUrl('index') => InvoiceResource::getNavigationLabel(),
            (string) $this->record->number,
        ];
    }
}
