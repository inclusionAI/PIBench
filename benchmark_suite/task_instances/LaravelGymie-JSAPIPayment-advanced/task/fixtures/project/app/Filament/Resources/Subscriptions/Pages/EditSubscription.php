<?php

namespace App\Filament\Resources\Subscriptions\Pages;

use App\Filament\Resources\Subscriptions\SubscriptionResource;
use App\Models\Member;
use App\Models\Subscription;
use Filament\Actions\DeleteAction;
use Filament\Actions\ForceDeleteAction;
use Filament\Actions\RestoreAction;
use Filament\Actions\ViewAction;
use Filament\Resources\Pages\EditRecord;

/**
 * @property-read Subscription $record
 */
class EditSubscription extends EditRecord
{
    protected static string $resource = SubscriptionResource::class;

    public function getTitle(): string
    {
        return __('app.actions.edit', ['resource' => SubscriptionResource::getModelLabel()]);
    }

    protected function getHeaderActions(): array
    {
        return [
            ViewAction::make(),
            DeleteAction::make(),
            ForceDeleteAction::make(),
            RestoreAction::make(),
        ];
    }

    public function getBreadcrumbs(): array
    {
        $member = $this->record->member;
        assert($member instanceof Member);

        return [
            __('app.navigation.groups.memberships'),
            SubscriptionResource::getUrl('index') => SubscriptionResource::getNavigationLabel(),
            $member->name,
        ];
    }
}
