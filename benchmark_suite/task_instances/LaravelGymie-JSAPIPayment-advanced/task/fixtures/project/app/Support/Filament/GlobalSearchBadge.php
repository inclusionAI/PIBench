<?php

namespace App\Support\Filament;

use App\Enums\Status;
use Illuminate\Support\Facades\Blade;
use Illuminate\Support\HtmlString;

final class GlobalSearchBadge
{
    public static function status(Status|string|null $status): HtmlString|string
    {
        $statusEnum = match (true) {
            $status instanceof Status => $status,
            is_string($status) => Status::tryFrom($status),
            default => null,
        };

        if (! $statusEnum) {
            return is_string($status) ? ucfirst($status) : '';
        }

        $color = $statusEnum->getColor();
        $label = $statusEnum->getLabel();

        return new HtmlString(
            Blade::render(
                '<x-filament::badge :color="$color" size="sm">{{ $label }}</x-filament::badge>',
                compact('color', 'label'),
            ),
        );
    }
}
