<?php

namespace App\Filament\Widgets\Analytics;

use App\Helpers\Helpers;
use App\Services\Analytics\AnalyticsService;
use App\Support\Analytics\AnalyticsDateRange;
use Carbon\CarbonImmutable;
use Filament\Support\Facades\FilamentColor;
use Filament\Widgets\Widget;
use Illuminate\Support\Collection;

/**
 * Spending overview card showing expense category breakdown for the selected period.
 *
 * This widget is intentionally not a Chart.js widget, so it can render a "stacked bar"
 * and a compact category list (similar to common analytics dashboards).
 */
class ExpenseCategoriesDoughnutChartWidget extends Widget
{
    protected static ?int $sort = -39;

    /**
     * @var view-string
     */
    protected string $view = 'filament.widgets.analytics.expense-spending-overview';

    /**
     * Selected range key for this widget.
     *
     * This powers the default widget select filter UI in the header.
     */
    public ?string $filter = '6months';

    /**
     * @var int | string | array<string, int | null>
     */
    protected int|string|array $columnSpan = [
        'default' => 1,
        'md' => 2,
    ];

    /**
     * Range filters for the default widget select UI.
     *
     * @return array<string, string>
     */
    public function getFilters(): array
    {
        return [
            '7days' => __('app.analytics.ranges.7days'),
            '30days' => __('app.analytics.ranges.30days'),
            'quarter' => __('app.analytics.ranges.quarter'),
            '6months' => __('app.analytics.ranges.6months'),
            'ytd' => __('app.analytics.ranges.ytd'),
        ];
    }

    /**
     * Resolve the date range used for this widget.
     */
    private function resolveRange(): AnalyticsDateRange
    {
        $rangeKey = $this->filter ?: '6months';

        $today = CarbonImmutable::today(\App\Support\AppConfig::timezone());
        $monthStart = $today->startOfMonth();

        [$start, $end] = match ($rangeKey) {
            '7days' => [$today->subDays(6), $today],
            '30days' => [$today->subDays(29), $today],
            'quarter' => [$today->startOfQuarter(), $today],
            'ytd' => [$today->startOfYear(), $today],
            default => [$monthStart->subMonthsNoOverflow(5), $today],
        };

        return new AnalyticsDateRange(
            $start->startOfDay(),
            $end->endOfDay(),
        );
    }

    /**
     * Resolve a registered Filament color shade (or return a fallback).
     *
     * @param  array<int | string, string | int> | null  $palette
     */
    private function colorShade(?array $palette, int|string $shade, string $fallback): string
    {
        if (is_array($palette)) {
            $value = $palette[$shade] ?? null;
            if (is_string($value) && filled($value)) {
                return $value;
            }

            $fallbackValue = $palette[500] ?? $palette['500'] ?? null;
            if (is_string($fallbackValue) && filled($fallbackValue)) {
                return $fallbackValue;
            }
        }

        return $fallback;
    }

    /**
     * Segment color palette for expense categories.
     *
     * Colors are resolved from the panel color configuration registered in
     * `app/Providers/Filament/AdminPanelProvider.php`.
     *
     * @return array<int, string>
     */
    private function segmentPalette(): array
    {
        $primary = FilamentColor::getColor('primary');
        $info = FilamentColor::getColor('info');
        $warning = FilamentColor::getColor('warning');
        $success = FilamentColor::getColor('success');

        return [
            $this->colorShade($primary, 400, '#1c908d'),
            $this->colorShade($primary, 600, '#0e5c5a'),
            $this->colorShade($info, 500, '#3B82F6'),
            $this->colorShade($warning, 500, '#F97316'),
            $this->colorShade($success, 500, '#10B981'),
        ];
    }

    /**
     * Color used for the "Other" segment.
     */
    private function otherSegmentColor(): string
    {
        $gray = FilamentColor::getColor('gray');

        return $this->colorShade($gray, 400, '#94A3B8');
    }

    /**
     * @return Collection<int, array{label: string, total: float, flex: float, color: string}>
     */
    private function buildSegments(AnalyticsDateRange $range): Collection
    {
        $rows = app(AnalyticsService::class)->expenseCategoryBreakdownForChart($range, 5);

        $palette = $this->segmentPalette();
        $otherColor = $this->otherSegmentColor();

        return $rows
            ->values()
            ->map(function (array $row, int $index) use ($palette, $otherColor): array {
                $category = (string) $row['category'];
                $resolvedLabel = Helpers::getExpenseCategoryLabel($category);
                $label = (string) ($category === 'Other'
                    ? __('app.analytics.other')
                    : (is_string($resolvedLabel) && filled($resolvedLabel) ? $resolvedLabel : $category));

                return [
                    'label' => $label,
                    'total' => (float) $row['total'],
                    'flex' => (float) max((float) $row['total'], 0),
                    'color' => $category === 'Other'
                        ? $otherColor
                        : ($palette[$index] ?? $palette[max(array_key_last($palette) ?? 0, 0)]),
                ];
            })
            ->filter(fn (array $segment): bool => $segment['flex'] > 0)
            ->values();
    }

    /**
     * @return array<string, mixed>
     */
    protected function getViewData(): array
    {
        $range = $this->resolveRange();

        $service = app(AnalyticsService::class);
        $expenses = (float) $service->financialMetrics($range)['expenses'];

        $segments = $this->buildSegments($range);

        return [
            'heading' => __('app.widgets.total_expense'),
            'totalExpense' => Helpers::formatCurrency($expenses),
            'segments' => $segments,
        ];
    }
}
