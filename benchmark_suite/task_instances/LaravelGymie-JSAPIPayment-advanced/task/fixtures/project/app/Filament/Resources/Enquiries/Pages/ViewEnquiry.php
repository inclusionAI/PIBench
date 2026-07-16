<?php

namespace App\Filament\Resources\Enquiries\Pages;

use App\Enums\Status;
use App\Filament\Resources\Enquiries\EnquiryResource;
use App\Filament\Resources\Members\MemberResource;
use App\Models\Enquiry;
use Filament\Actions\Action;
use Filament\Actions\DeleteAction;
use Filament\Actions\EditAction;
use Filament\Resources\Pages\ViewRecord;

/**
 * @property-read Enquiry $record
 */
class ViewEnquiry extends ViewRecord
{
    protected static string $resource = EnquiryResource::class;

    public function getTitle(): string
    {
        return __('app.titles.record', [
            'resource' => EnquiryResource::getModelLabel(),
            'name' => $this->record->name,
        ]);
    }

    protected function getHeaderActions(): array
    {
        return [
            EditAction::make(),
            DeleteAction::make(),
            Action::make('convert_to_member')
                ->label(__('app.actions.convert_to_member'))
                ->icon('heroicon-s-arrows-right-left')
                ->color('success')
                ->requiresConfirmation()
                ->visible(fn (Enquiry $record) => $record->status === Status::Lead)
                ->url(fn (Enquiry $record) => MemberResource::getUrl(
                    'create',
                    ['enquiry_id' => $record->id],
                )),
        ];
    }

    public function getBreadcrumbs(): array
    {
        return [
            __('app.navigation.groups.sales'),
            EnquiryResource::getUrl('index') => EnquiryResource::getNavigationLabel(),
            $this->record->name,
        ];
    }
}
