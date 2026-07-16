<?php

namespace App\Filament\Widgets\Analytics;

use App\Helpers\Helpers;
use App\Services\Analytics\AnalyticsService;
use App\Support\Analytics\AnalyticsDateRange;
use Filament\Widgets\Concerns\InteractsWithPageFilters;
use Filament\Widgets\StatsOverviewWidget;
use Filament\Widgets\StatsOverviewWidget\Stat;
use Illuminate\Support\Facades\Blade;
use Illuminate\Support\HtmlString;

/**
 * Financial overview widget for key revenue and expense KPIs.
 */
class FinancialMetricsWidget extends StatsOverviewWidget
{
    use InteractsWithPageFilters;

    protected static ?int $sort = -40;

    /**
     * @var int | string | array<string, int | null>
     */
    protected int|string|array $columnSpan = [
        'default' => 1,
        'md' => 2,
    ];

    /**
     * @var int | array<string, ?int> | null
     */
    protected int|array|null $columns = 2;

    /**
     * Build an inline delta label for KPI cards.
     *
     * @return array{label: string, icon: string|null, class: string}
     */
    private function deltaInline(float $current, float $previous): array
    {
        if ($previous <= 0) {
            if ($current <= 0) {
                return [
                    'label' => '0%',
                    'icon' => 'heroicon-o-minus',
                    'class' => 'text-gray-500',
                ];
            }

            return [
                'label' => '+'.Helpers::formatCurrency($current),
                'icon' => 'heroicon-o-arrow-trending-up',
                'class' => 'text-success-600 dark:text-success-400',
            ];
        }

        $pct = (($current - $previous) / $previous) * 100;
        $pct = round($pct, 1);

        if ($pct === 0.0) {
            return [
                'label' => '0%',
                'icon' => 'heroicon-o-minus',
                'class' => 'text-gray-500',
            ];
        }

        if ($pct > 0) {
            return [
                'label' => "+{$pct}%",
                'icon' => 'heroicon-o-arrow-trending-up',
                'class' => 'text-success-600 dark:text-success-400',
            ];
        }

        $pct = abs($pct);

        return [
            'label' => "-{$pct}%",
            'icon' => 'heroicon-o-arrow-trending-down',
            'class' => 'text-danger-600 dark:text-danger-400',
        ];
    }

    /**
     * Render a KPI value with an inline delta.
     *
     * @param  array{label: string, icon: string|null, class: string}  $delta
     */
    private function valueWithDelta(string $value, array $delta): HtmlString
    {
        $value = e($value);
        $deltaLabel = e($delta['label']);
        $deltaClass = e($delta['class']);

        $deltaIcon = null;
        if (filled($delta['icon'])) {
            $deltaIcon = Blade::render(
                '<x-filament::icon :icon="$icon" class="h-4 w-4 text-current" />',
                ['icon' => $delta['icon']],
            );
        }

        return new HtmlString(<<<HTML
<div class="flex items-baseline gap-2 my-2">
    <span>{$value}</span>
    <span class="text-sm font-semibold {$deltaClass} inline-flex items-center gap-1">{$deltaLabel}{$deltaIcon}</span>
</div>
HTML);
    }

    /**
     * Tailwind selector classes that color the main stat icon using the panel primary color.
     */
    private function primaryStatIconClasses(): string
    {
        return '[&_.fi-wi-stats-overview-stat-label-ctn>.fi-icon]:text-primary-400 dark:[&_.fi-wi-stats-overview-stat-label-ctn>.fi-icon]:text-primary-400';
    }

    /**
     * @return array<int, Stat>
     */
    protected function getStats(): array
    {
        $range = AnalyticsDateRange::fromFilters($this->pageFilters);
        $service = app(AnalyticsService::class);
        $metrics = $service->financialMetrics($range);

        $days = $range->end->diffInDays($range->start) + 1;
        $previousRange = new AnalyticsDateRange(
            $range->start->subDays($days),
            $range->end->subDays($days),
        );
        $previous = $service->financialMetrics($previousRange);

        $netRevenueDelta = $this->deltaInline($metrics['net_revenue'], $previous['net_revenue']);
        $collectedDelta = $this->deltaInline($metrics['collected'], $previous['collected']);
        $outstandingDelta = $this->deltaInline($metrics['outstanding'], $previous['outstanding']);
        $profitDelta = $this->deltaInline($metrics['profit'], $previous['profit']);

        return [
            Stat::make(
                __('app.widgets.net_revenue'),
                $this->valueWithDelta(Helpers::formatCurrency($metrics['net_revenue']), $netRevenueDelta),
            )
                ->icon('heroicon-o-banknotes')
                ->extraAttributes(['class' => $this->primaryStatIconClasses()])
                ->description(__('app.widgets.vs_previous_period', ['count' => Helpers::formatCurrency($previous['net_revenue'])]))
                ->descriptionColor('gray'),
            Stat::make(
                __('app.widgets.total_collected'),
                $this->valueWithDelta(Helpers::formatCurrency($metrics['collected']), $collectedDelta),
            )
                ->icon('heroicon-o-arrow-down-tray')
                ->extraAttributes(['class' => $this->primaryStatIconClasses()])
                ->description(__('app.widgets.vs_previous_period', ['count' => Helpers::formatCurrency($previous['collected'])]))
                ->descriptionColor('gray'),
            Stat::make(
                __('app.widgets.outstanding_payments'),
                $this->valueWithDelta(Helpers::formatCurrency($metrics['outstanding']), $outstandingDelta),
            )
                ->icon('heroicon-o-clock')
                ->extraAttributes(['class' => $this->primaryStatIconClasses()])
                ->description(__('app.widgets.vs_previous_period', ['count' => Helpers::formatCurrency($previous['outstanding'])]))
                ->descriptionColor('gray'),
            Stat::make(
                __('app.widgets.profit'),
                $this->valueWithDelta(Helpers::formatCurrency($metrics['profit']), $profitDelta),
            )
                ->icon('heroicon-o-chart-bar-square')
                ->extraAttributes(['class' => $this->primaryStatIconClasses()])
                ->description(__('app.widgets.vs_previous_period', ['count' => Helpers::formatCurrency($previous['profit'])]))
                ->descriptionColor('gray'),
        ];
    }
}
