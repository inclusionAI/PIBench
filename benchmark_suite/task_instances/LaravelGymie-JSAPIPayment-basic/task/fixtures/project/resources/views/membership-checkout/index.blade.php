<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Gymie Membership Checkout</title>
    <style>
        body {
            margin: 0;
            background: #f7f8fa;
            color: #111827;
            font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }

        main {
            width: min(920px, calc(100vw - 40px));
            margin: 0 auto;
            padding: 40px 0;
        }

        section {
            margin-top: 20px;
            padding: 22px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: #ffffff;
        }

        h1 {
            margin: 0;
            font-size: 34px;
            line-height: 1.1;
        }

        h2 {
            margin: 0 0 14px;
            font-size: 20px;
        }

        p, li {
            color: #4b5563;
            line-height: 1.6;
        }

        code {
            padding: 2px 6px;
            border-radius: 6px;
            background: #f3f4f6;
            color: #111827;
        }
    </style>
</head>
<body>
<main>
    <h1>Gymie Membership Checkout</h1>
    <p>
        This environment keeps a runnable gym membership-card ordering flow for
        a mobile mini program. Payment integration is intentionally absent from
        the starter application.
    </p>

    <section>
        <h2>Available plans</h2>
        <ul>
            @foreach ($plans as $plan)
                <li>{{ $plan->name }} / CNY {{ number_format((float) $plan->amount, 2) }} / {{ $plan->days }} days</li>
            @endforeach
        </ul>
    </section>

    <section>
        <h2>Business API</h2>
        <ul>
            <li><code>GET /api/membership-checkout/plans</code> lists cards for sale.</li>
            <li><code>POST /api/membership-checkout/orders</code> creates a local membership order.</li>
            <li><code>GET /api/membership-checkout/orders/{checkout_no}</code> returns order status.</li>
        </ul>
    </section>
</main>
</body>
</html>
