<!doctype html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}" dir="{{ app()->getLocale() === 'ar' ? 'rtl' : 'ltr' }}">

<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ __('app.invoices.pdf.title', ['number' => $invoice->number]) }}</title>
    @php
        /**
         * Inter font files are included locally for PDF rendering.
         *
         * DomPDF does not support WOFF2, so we ship TTF weights under `public/fonts/inter`.
         *
         * @var array<int, string> $interFilesByWeight
         */
        $interFilesByWeight = [
            400 => 'Inter-Regular.ttf',
            500 => 'Inter-Medium.ttf',
            600 => 'Inter-SemiBold.ttf',
            700 => 'Inter-Bold.ttf',
            800 => 'Inter-ExtraBold.ttf',
            900 => 'Inter-Black.ttf',
        ];
    @endphp
    <style>
        @foreach ($interFilesByWeight as $weight => $filename)
        @if (file_exists(public_path("fonts/inter/{$filename}")))
        @font-face {
            font-family: 'Inter';
            font-style: normal;
            font-weight: {{ $weight }};
            font-display: swap;
            src: url('file://{{ public_path("fonts/inter/{$filename}") }}') format('truetype');
        }
        @endif
        @endforeach

        @page {
            size: A4 portrait;
            margin: 0mm;
        }

        html,
        body {
            margin: 0;
            padding: 0;
        }

        :root {
            --ink: #0b1220;
            --darkgreen: #021f1e;
            --green: #10b981;
            --green-2: #0ea371;
            --table-x: 8px;

            --text: #111827;
            --muted: #6b7280;
            --line: #e5e7eb;
            --bg: #ffffff;
            --soft: #f9fafb;
        }

        * {
            box-sizing: border-box;
        }

        body {
            font-family: Inter, sans-serif;
            color: var(--text);
            background: var(--bg);
        }

        .shell {
            width: 100%;
            border-radius: 0;
        }

        .header {
            background: var(--darkgreen);
            color: #fff;
            padding: 26px 28px;
        }

        .brand {
            font-size: 30px;
            font-weight: 800;
            letter-spacing: 0.5px;
            margin: 0;
        }

        .brand-accent {
            color: var(--green);
        }

        .subtext {
            margin: 2px 0 0 0;
            font-size: 13px;
            color: #90a1b9;
        }

        .header-right {
            text-align: right;
            vertical-align: top;
        }

        .badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 800;
            letter-spacing: 0.8px;
            text-transform: uppercase;
            border: 1px solid rgba(255, 255, 255, 0.14);
        }

        .badge-paid {
            background: rgba(16, 185, 129, 0.18);
            color: #34d399;
            border-color: rgba(52, 211, 153, 0.35);
        }

        .badge-overdue {
            background: rgba(245, 158, 11, 0.18);
            color: #fbbf24;
            border-color: rgba(251, 191, 36, 0.35);
        }

        .badge-muted {
            background: rgba(148, 163, 184, 0.12);
            color: #cbd5e1;
            border-color: rgba(148, 163, 184, 0.25);
        }

        .invoice-meta {
            margin-top: 10px;
            font-size: 13px;
            font-weight: 600;
            color: #90a1b9;
        }

        .accent-line {
            height: 4px;
            background: var(--green);
        }

        .section {
            padding: 22px 28px;
            padding-bottom: 88px;
        }

        .label {
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
            color: #9ca3af;
            margin: 0 0 10px 0;
        }

        .value-title {
            font-size: 18px;
            font-weight: 700;
            margin: 0;
        }

        .value-line {
            margin-top: 2px;
            font-size: 13px;
            font-weight: 500;
            color: #6a7282;
            line-height: 1.4;
        }

        .divider {
            border-top: 1px solid var(--line);
            margin: 18px 0;
        }

        .items {
            width: 100%;
            margin-top: 60px;
            border-collapse: collapse;
        }

        .items th,
        .items td {
            border-bottom: 1px solid var(--line);
            padding: 14px var(--table-x);
            text-align: left;
            vertical-align: top;
            font-size: 12.5px;
        }

        .items th {
            color: #9ca3af;
            font-weight: 800;
            letter-spacing: 1px;
            text-transform: uppercase;
            background: transparent;
        }

        .right {
            text-align: right;
        }

        .money {
            font-family: DejaVu Sans, Inter, sans-serif;
        }

        .desc-title {
            font-size: 15px;
            font-weight: 700;
            margin: 0;
        }

        .desc-sub {
            margin-top: 6px;
            font-size: 12.5px;
            color: var(--muted);
        }

        .totals {
            width: 250px;
            margin-left: auto;
            border-collapse: collapse;
            margin-top: 18px;
            table-layout: fixed;
        }

        .totals td {
            padding: 8px var(--table-x);
            font-size: 14px;
            font-weight: 700;
            color: #4a5565;
        }

        .totals .strong {
            color: #4a5565;
            font-weight: 800;
        }

        .totals .total-row td {
            padding-top: 0px;
            font-size: 18px;
            font-weight: 800;
            color: var(--text);
        }

        .totals .total-row .amount {
            color: var(--green-2);
        }

        .callout {
            margin-top: 18px;
            border-left: 4px solid rgba(16, 185, 129, 0.45);
            background: rgba(16, 185, 129, 0.08);
            padding: 14px 16px;
            border-radius: 4px;
        }

        .callout-title {
            font-size: 14px;
            font-weight: 700;
            text-transform: capitalize;
            color: var(--green-2);
            margin: 0 0 0px 0;
        }

        .callout-body {
            margin: 0;
            color: var(--text);
            font-size: 12.5px;
            line-height: 1.4;
        }

        .footer {
            background: #064e3b;
            color: #d1fae5;
            text-align: center;
            padding: 16px 18px;
            font-size: 10.5px;
            letter-spacing: 3px;
            text-transform: uppercase;
            position: fixed;
            left: 0;
            right: 0;
            bottom: 0;
        }
    </style>
</head>

<body>
    @php
    $gymName = (string) data_get($settings, 'general.gym_name', 'Gymie');
    $gymAddress = (string) data_get($settings, 'general.address', '');
    $gymEmail = (string) data_get($settings, 'general.gym_email', '');
    $gymContact = (string) data_get($settings, 'general.gym_contact', '');
    $nameType = (string) data_get($settings, 'invoice.name_type', 'gym_name');

    $status = $invoice->status?->value ?? (string) $invoice->status;
    $statusLabel = $invoice->getDisplayStatusLabel();
    $statusBadgeClass = match ($status) {
    'paid' => 'badge-paid',
    'overdue' => 'badge-overdue',
    default => 'badge-muted',
    };

    $gross = max((float) ($invoice->subscription_fee ?? 0), 0);
    $paidAmount = (float) ($invoice->paid_amount ?? 0);
    $dueAmount = (float) ($invoice->due_amount ?? 0);
    $taxRatePercent = $gross > 0 ? (((float) ($invoice->tax ?? 0)) / $gross) * 100 : 0;
    $taxRatePercent = $taxRatePercent > 0 ? round($taxRatePercent, 2) : 0;
    $taxRatePercentLabel = rtrim(rtrim(number_format($taxRatePercent, 2, '.', ''), '0'), '.');

    $gymDomain = preg_replace('/\\s+/', '', strtolower($gymName));
    $gymDomain = preg_replace('/[^a-z0-9]+/', '', (string) $gymDomain);
    @endphp

    <div class="shell">
        <div class="header">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="vertical-align: top;">
                        <p class="brand">
                            @if ($nameType === 'gym_name')
                            {{ strtoupper($gymName) }}
                            @else
                            <span>{{ strtoupper($gymName) }}</span>
                            @endif
                        </p>
                        @if (filled($gymAddress))
                        <p class="subtext">{{ $gymAddress }}</p>
                        @endif
                        @if (filled($gymEmail) || filled($gymContact))
                        <p class="subtext">
                            @if (filled($gymEmail))
                            {{ $gymEmail }}
                            @endif
                            @if (filled($gymEmail) && filled($gymContact))
                            |
                            @endif
                            @if (filled($gymContact))
                            {{ $gymContact }}
                            @endif
                        </p>
                        @endif
                    </td>
                    <td class="header-right">
                        <span class="badge {{ $statusBadgeClass }}">{{ $statusLabel }}</span>
                        <div class="invoice-meta">{{ __('app.invoices.pdf.invoice_number', ['number' => $invoice->number]) }}</div>
                    </td>
                </tr>
            </table>
        </div>

        <div class="accent-line"></div>

        <div class="section">
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="width: 60%; vertical-align: top; padding-right: 18px;">
                        <p class="label">{{ __('app.invoices.pdf.member_details') }}</p>
                        <p class="value-title">{{ $member?->name ?? '-' }}</p>
                        <div class="value-line">
                            @if (filled($member?->code))
                            <div>{{ __('app.fields.id') }}: {{ $member->code }}</div>
                            @endif
                            @if (filled($member?->email))
                            <div>{{ $member->email }}</div>
                            @endif
                            @if (filled($member?->contact))
                            <div>{{ $member->contact }}</div>
                            @endif
                        </div>
                    </td>
	                    <td style="width: 40%; vertical-align: top; text-align: right;">
	                        <p class="label">{{ __('app.invoices.pdf.billing_cycle') }}</p>
	                        <p class="value-title">
	                            {{ optional($invoice->date)->translatedFormat('F d, Y') }}
	                        </p>
	                        <div class="value-line">
	                            @if ($subscription)
	                            <div class="muted">
	                                {{ optional($subscription->start_date)->translatedFormat('d M Y') }} - {{ optional($subscription->end_date)->translatedFormat('d M Y') }}
	                            </div>
	                            @endif
	                        </div>
	                    </td>
                </tr>
            </table>

            <table class="items" aria-label="Invoice line items">
                <thead>
                    <tr>
                        <th>{{ __('app.fields.plan') }}</th>
                        <th class="right" style="width: 0px;">{{ __('app.fields.amount') }}</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>
                            <p class="desc-title">{{ $plan?->name ?? __('app.invoices.pdf.membership') }}</p>
                            @if (filled($plan?->description))
                            <div class="desc-sub">{{ $plan->description }}</div>
                            @elseif ($subscription)
                            <div class="desc-sub">{{ __('app.invoices.pdf.membership_description') }}</div>
                            @endif
                        </td>
                        <td class="right" style="font-size: 16px; font-weight: 800; text-align: right;"><span class="money">{{ \App\Helpers\Helpers::formatCurrency($gross) }}</span></td>
                    </tr>
                </tbody>
            </table>

            @if (filled($invoice->discount_note))
            <div class="callout" aria-label="Discount note">
                <p class="callout-title">{{ __('app.fields.discount_note') }}</p>
                <p class="callout-body">{{ $invoice->discount_note }}</p>
            </div>
            @endif

            <table class="totals" aria-label="Invoice totals">
                <colgroup>
                    <col>
                    <col style="width: 140px;">
                </colgroup>
                <tbody>
                    <tr>
                        <td>{{ __('app.invoices.pdf.subtotal') }}</td>
                        <td class="right strong"><span class="money">{{ \App\Helpers\Helpers::formatCurrency($gross) }}</span></td>
                    </tr>
                    @if ((float) ($invoice->discount_amount ?? 0) > 0)
                    <tr>
                        <td>{{ __('app.fields.discount') }}</td>
                        <td class="right strong">-<span class="money">{{ \App\Helpers\Helpers::formatCurrency($invoice->discount_amount) }}</span></td>
                    </tr>
                    @endif
                    @if ((float) ($invoice->tax ?? 0) > 0)
                    <tr>
                        <td>
                            {{ __('app.fields.tax') }} @if ($taxRatePercentLabel !== '0') ({{ $taxRatePercentLabel }}%) @endif
                        </td>
                        <td class="right strong"><span class="money">{{ \App\Helpers\Helpers::formatCurrency($invoice->tax) }}</span></td>
                    </tr>
                    @endif
                    @if ($paidAmount > 0 && $dueAmount > 0)
                    <tr>
                        <td>{{ __('app.fields.paid') }}</td>
                        <td class="right strong"><span class="money">{{ \App\Helpers\Helpers::formatCurrency($paidAmount) }}</span></td>
                    </tr>
                    @endif
                    <tr>
                        <td colspan="2">
                            <div style="background-color: var(--green); height: 2px; margin-left: 10px; margin-right: 10px; width: 100%;"></div>
                        </td>
                    </tr>
                    <tr class="total-row">
                        <td>
                            {{ $dueAmount <= 0 ? __('app.invoices.pdf.total_paid') : __('app.invoices.pdf.total_due') }}
                        </td>
                        <td class="right amount">
                            <span class="money">{{ \App\Helpers\Helpers::formatCurrency($dueAmount <= 0 ? $paidAmount : $dueAmount) }}</span>
                        </td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div class="footer">
            {{ __('app.invoices.pdf.footer_tagline', ['domain' => filled($gymDomain) ? $gymDomain : 'gymie']) }}
        </div>
    </div>
</body>

</html>
