<!doctype html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{{ __('app.invoices.error.title') }}</title>
        <style>
            body {
                margin: 0;
                font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji";
                background: #f9fafb;
                color: #111827;
            }

            .wrap {
                max-width: 720px;
                margin: 60px auto;
                padding: 0 16px;
            }

            .card {
                background: #fff;
                border: 1px solid #e5e7eb;
                border-radius: 14px;
                padding: 18px;
            }

            h1 {
                font-size: 18px;
                margin: 0 0 6px 0;
            }

            p {
                margin: 0 0 12px 0;
                color: #4b5563;
                line-height: 1.5;
                font-size: 13px;
            }

            ul {
                margin: 10px 0 0 18px;
                padding: 0;
                color: #111827;
                font-size: 13px;
            }

            .meta {
                margin-top: 14px;
                font-size: 12px;
                color: #6b7280;
            }

            .btn {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 10px 12px;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                background: #ffffff;
                text-decoration: none;
                color: #111827;
                font-weight: 600;
                font-size: 13px;
            }
        </style>
    </head>
    <body>
        <div class="wrap">
            <div class="card">
                <h1>{{ __('app.invoices.error.heading') }}</h1>
                <p>
                    {{ __('app.invoices.error.description') }}
                </p>

                @if (! empty($missing))
                    <p><strong>{{ __('app.invoices.error.missing') }}:</strong></p>
                    <ul>
                        @foreach ($missing as $item)
                            <li>{{ $item }}</li>
                        @endforeach
                    </ul>
                @endif

                <div style="margin-top: 16px;">
                    <a class="btn" href="{{ url()->previous() }}">{{ __('app.actions.back') }}</a>
                </div>

                @if (isset($invoice))
                    <div class="meta">
                        {{ __('app.resources.invoices.singular') }}: {{ $invoice->number ?: '#' . $invoice->id }}
                    </div>
                @endif
            </div>
        </div>
    </body>
</html>
