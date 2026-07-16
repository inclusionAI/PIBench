<?php

namespace App\Filament\Resources\Subscriptions\Pages;

use App\Filament\Resources\Subscriptions\SubscriptionResource;
use App\Models\Member;
use App\Models\Subscription;
use Filament\Actions\DeleteAction;
use Filament\Actions\EditAction;
use Filament\Resources\Pages\ViewRecord;

/**
 * @property-read Subscription $record
 */
class ViewSubscription extends ViewRecord
{
    protected static string $resource = SubscriptionResource::class;

    public function getTitle(): string
    {
        $member = $this->record->member;
        assert($member instanceof Member);

        return __('app.titles.record', [
            'resource' => SubscriptionResource::getModelLabel(),
            'name' => $member->name,
        ]);
    }

    protected function getHeaderActions(): array
    {
        return [
            EditAction::make()
                ->hidden(fn (): bool => in_array($this->record->status?->value, ['expired', 'renewed'], true)),
            DeleteAction::make(),
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
