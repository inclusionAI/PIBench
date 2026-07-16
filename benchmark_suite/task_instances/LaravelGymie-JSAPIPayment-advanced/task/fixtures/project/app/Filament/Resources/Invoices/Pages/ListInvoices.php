<?php

namespace App\Filament\Resources\Invoices\Pages;

use App\Enums\Status;
use App\Filament\Resources\Invoices\InvoiceResource;
use App\Models\Invoice;
use Filament\Resources\Pages\ListRecords;
use Filament\Schemas\Components\Tabs\Tab;
use Illuminate\Database\Eloquent\Builder;

class ListInvoices extends ListRecords
{
    protected static string $resource = InvoiceResource::class;

    protected function getHeaderActions(): array
    {
        return [];
    }

    public function getTabs(): array
    {
        return [
            'all' => Tab::make(__('app.common.all')),
            'issued' => Tab::make(__('app.status.issued'))
                ->badge(Invoice::query()->where('status', 'issued')->count())
                ->badgeColor(Status::Issued->getColor())
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'issued')),
            'partial' => Tab::make(__('app.status.partially_paid'))
                ->badge(Invoice::query()->where('status', 'partial')->count())
                ->badgeColor(Status::Partial->getColor())
                ->label(__('app.status.partial'))
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'partial')),
            'overdue' => Tab::make(__('app.status.overdue'))
                ->badge(Invoice::query()->where('status', 'overdue')->count())
                ->badgeColor(Status::Overdue->getColor())
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'overdue')),
            'paid' => Tab::make(__('app.status.paid'))
                ->badge(Invoice::query()->where('status', 'paid')->count())
                ->badgeColor(Status::Paid->getColor())
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'paid')),
            'refund' => Tab::make(__('app.status.refund'))
                ->badge(Invoice::query()->where('status', 'refund')->count())
                ->badgeColor(Status::Refund->getColor())
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'refund')),
            'cancelled' => Tab::make(__('app.status.cancelled'))
                ->badge(Invoice::query()->where('status', 'cancelled')->count())
                ->badgeColor(Status::Cancelled->getColor())
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'cancelled')),
        ];
    }

    public function getBreadcrumbs(): array
    {
        return [
            __('app.navigation.groups.billing'),
            InvoiceResource::getUrl('index') => InvoiceResource::getNavigationLabel(),
        ];
    }
}
