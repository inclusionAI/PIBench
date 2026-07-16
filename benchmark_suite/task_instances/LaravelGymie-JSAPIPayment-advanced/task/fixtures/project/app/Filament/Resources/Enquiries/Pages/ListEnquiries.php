<?php

namespace App\Filament\Resources\Enquiries\Pages;

use App\Enums\Status;
use App\Filament\Resources\Enquiries\EnquiryResource;
use App\Models\Enquiry;
use Filament\Actions\CreateAction;
use Filament\Resources\Pages\ListRecords;
use Filament\Schemas\Components\Tabs\Tab;
use Illuminate\Database\Eloquent\Builder;

class ListEnquiries extends ListRecords
{
    protected static string $resource = EnquiryResource::class;

    protected function getHeaderActions(): array
    {
        return [
            CreateAction::make()
                ->icon('heroicon-m-plus')
                ->label(__('app.actions.new', ['resource' => EnquiryResource::getModelLabel()]))
                ->hidden(! Enquiry::exists()),
        ];
    }

    public function getBreadcrumbs(): array
    {
        return [
            __('app.navigation.groups.sales'),
            EnquiryResource::getNavigationLabel(),
        ];
    }

    public function getTabs(): array
    {
        return [
            'all' => Tab::make(__('app.common.all')),
            'lead' => Tab::make(__('app.status.lead'))
                ->badge(Enquiry::query()->where('status', 'lead')->count())
                ->badgeColor(Status::Lead->getColor())
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'lead')),
            'member' => Tab::make(__('app.status.member'))
                ->badge(Enquiry::query()->where('status', 'member')->count())
                ->badgeColor(Status::Member->getColor())
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'member')),
            'lost' => Tab::make(__('app.status.lost'))
                ->badge(Enquiry::query()->where('status', 'lost')->count())
                ->badgeColor(Status::Lost->getColor())
                ->modifyQueryUsing(fn (Builder $query): Builder => $query->where('status', 'lost')),
        ];
    }
}
