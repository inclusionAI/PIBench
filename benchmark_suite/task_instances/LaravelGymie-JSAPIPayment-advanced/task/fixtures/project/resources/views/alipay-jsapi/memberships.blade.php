<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="csrf-token" content="{{ csrf_token() }}">
    <title>Gymie Membership Checkout</title>
    <link rel="preconnect" href="https://images.unsplash.com">
    <style>
        :root {
            color-scheme: light;
            --ink: #17211d;
            --muted: #64706a;
            --line: #d9e3de;
            --panel: #ffffff;
            --wash: #f5f8f3;
            --green: #177a57;
            --green-dark: #0f5f44;
            --coral: #d85d3a;
            --amber: #f2b84b;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            min-height: 100vh;
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            color: var(--ink);
            background: var(--wash);
        }

        button,
        input {
            font: inherit;
        }

        .page {
            min-height: 100vh;
            display: grid;
            grid-template-columns: minmax(280px, 0.9fr) minmax(360px, 1.1fr);
        }

        .visual {
            position: relative;
            min-height: 100vh;
            padding: 32px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            background:
                linear-gradient(180deg, rgba(12, 24, 19, 0.08), rgba(12, 24, 19, 0.74)),
                url("https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=1400&q=80") center/cover;
            color: #fff;
        }

        .brand {
            width: fit-content;
            padding: 10px 12px;
            border: 1px solid rgba(255, 255, 255, 0.42);
            background: rgba(0, 0, 0, 0.22);
            border-radius: 8px;
            font-weight: 800;
            letter-spacing: 0;
        }

        .visual h1 {
            max-width: 560px;
            margin: 0 0 14px;
            font-size: clamp(36px, 5vw, 72px);
            line-height: 0.96;
            letter-spacing: 0;
        }

        .visual p {
            max-width: 540px;
            margin: 0;
            color: rgba(255, 255, 255, 0.86);
            font-size: 18px;
            line-height: 1.55;
        }

        .checkout {
            padding: 34px clamp(18px, 4vw, 56px);
            display: grid;
            align-content: center;
            gap: 22px;
        }

        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }

        .topbar a {
            color: var(--green-dark);
            text-decoration: none;
            font-weight: 700;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            min-height: 30px;
            padding: 6px 10px;
            border: 1px solid var(--line);
            border-radius: 999px;
            background: #fff;
            color: var(--muted);
            font-size: 13px;
            font-weight: 700;
            white-space: nowrap;
        }

        .panel {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 8px;
            box-shadow: 0 24px 60px rgba(32, 47, 40, 0.08);
        }

        .panel-header,
        .summary,
        form {
            padding: 22px;
        }

        .panel-header {
            border-bottom: 1px solid var(--line);
        }

        .panel-header h2 {
            margin: 0 0 6px;
            font-size: 24px;
            letter-spacing: 0;
        }

        .panel-header p {
            margin: 0;
            color: var(--muted);
            line-height: 1.5;
        }

        .plans {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 10px;
            padding: 18px 22px 0;
        }

        .plan {
            min-height: 152px;
            padding: 14px;
            text-align: left;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #fff;
            color: var(--ink);
            cursor: pointer;
            transition: border-color 160ms ease, transform 160ms ease, box-shadow 160ms ease;
        }

        .plan:hover,
        .plan.is-selected {
            border-color: var(--green);
            box-shadow: 0 10px 24px rgba(23, 122, 87, 0.13);
            transform: translateY(-1px);
        }

        .plan strong {
            display: block;
            min-height: 42px;
            font-size: 16px;
            line-height: 1.3;
        }

        .plan span {
            display: block;
            color: var(--muted);
            font-size: 13px;
            line-height: 1.35;
        }

        .plan .price {
            margin-top: 14px;
            color: var(--green-dark);
            font-size: 24px;
            font-weight: 850;
        }

        form {
            display: grid;
            gap: 14px;
        }

        .fields {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }

        label {
            display: grid;
            gap: 7px;
            color: var(--muted);
            font-size: 13px;
            font-weight: 700;
        }

        input {
            width: 100%;
            min-height: 46px;
            padding: 10px 12px;
            border: 1px solid var(--line);
            border-radius: 6px;
            background: #fff;
            color: var(--ink);
            outline: none;
        }

        input:focus {
            border-color: var(--green);
            box-shadow: 0 0 0 3px rgba(23, 122, 87, 0.12);
        }

        .span-2 {
            grid-column: span 2;
        }

        .actions {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 10px;
            margin-top: 6px;
        }

        .primary,
        .secondary,
        .danger {
            min-height: 46px;
            padding: 0 16px;
            border-radius: 6px;
            border: 0;
            cursor: pointer;
            font-weight: 800;
        }

        .primary {
            background: var(--green);
            color: #fff;
        }

        .primary:hover {
            background: var(--green-dark);
        }

        .secondary {
            background: #17211d;
            color: #fff;
        }

        .danger {
            background: #fff;
            color: var(--coral);
            border: 1px solid rgba(216, 93, 58, 0.36);
        }

        button:disabled {
            opacity: 0.58;
            cursor: wait;
        }

        .status {
            min-height: 22px;
            color: var(--muted);
            font-size: 14px;
            line-height: 1.45;
        }

        .summary {
            display: none;
            border-top: 1px solid var(--line);
            background: #fbfcfa;
        }

        .summary.is-visible {
            display: grid;
            gap: 14px;
        }

        .summary h3 {
            margin: 0;
            font-size: 18px;
        }

        .grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
        }

        .metric {
            min-height: 74px;
            padding: 12px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: #fff;
        }

        .metric small {
            display: block;
            margin-bottom: 6px;
            color: var(--muted);
            font-weight: 700;
        }

        .metric code {
            overflow-wrap: anywhere;
            color: var(--ink);
            font-size: 13px;
        }

        .state {
            color: var(--green-dark);
            font-weight: 850;
        }

        .state.refunded,
        .state.failed {
            color: var(--coral);
        }

        @media (max-width: 980px) {
            .page {
                grid-template-columns: 1fr;
            }

            .visual {
                min-height: 38vh;
            }

            .visual h1 {
                font-size: 42px;
            }

            .checkout {
                align-content: start;
            }
        }

        @media (max-width: 720px) {
            .visual,
            .checkout {
                padding: 22px 16px;
            }

            .plans,
            .fields,
            .grid {
                grid-template-columns: 1fr;
            }

            .span-2 {
                grid-column: auto;
            }

            .plans {
                padding: 16px;
            }

            .panel-header,
            .summary,
            form {
                padding: 16px;
            }
        }
    </style>
</head>
<body>
<main class="page">
    <section class="visual" aria-label="Gym training floor">
        <div class="brand">Gymie</div>
        <div>
            <h1>Membership card checkout</h1>
            <p>Alipay JSAPI order flow for gym plans, subscription billing, invoices, refunds, and payment ledger records.</p>
        </div>
    </section>

    <section class="checkout">
        <div class="topbar">
            <span class="badge">{{ $demoMode ? 'Demo gateway' : 'Alipay gateway' }}</span>
            <a href="/">Admin</a>
        </div>

        <div class="panel">
            <div class="panel-header">
                <h2>Choose a membership</h2>
                <p>Pay inside Alipay with JSAPI or complete the benchmark flow in demo mode.</p>
            </div>

            @if ($plans->isEmpty())
                <div class="summary is-visible">
                    <h3>No plans found</h3>
                    <p class="status">Run the database seeders, then refresh this page.</p>
                </div>
            @else
                <div class="plans" id="plans">
                    @foreach ($plans as $plan)
                        <button
                            type="button"
                            class="plan {{ $loop->first ? 'is-selected' : '' }}"
                            data-plan-id="{{ $plan->id }}"
                            data-plan-name="{{ $plan->name }}"
                            data-plan-amount="{{ number_format((float) $plan->amount, 2, '.', '') }}"
                        >
                            <strong>{{ $plan->name }}</strong>
                            <span>{{ $plan->days }} days</span>
                            <span>{{ $plan->description }}</span>
                            <div class="price">¥{{ number_format((float) $plan->amount, 2) }}</div>
                        </button>
                    @endforeach
                </div>

                <form id="checkout-form">
                    <input type="hidden" name="plan_id" id="plan-id" value="{{ $plans->first()->id }}">
                    <div class="fields">
                        <label>
                            Member name
                            <input name="buyer_name" value="Benchmark Buyer" autocomplete="name" required>
                        </label>
                        <label>
                            Mobile
                            <input name="buyer_contact" value="13800138000" autocomplete="tel">
                        </label>
                        <label class="span-2">
                            Email
                            <input name="buyer_email" value="benchmark-buyer@example.com" autocomplete="email">
                        </label>
                        <label>
                            buyer_open_id
                            <input name="buyer_open_id" placeholder="Alipay mini program user open id">
                        </label>
                        <label>
                            buyer_id
                            <input name="buyer_id" placeholder="Alipay user id">
                        </label>
                    </div>

                    <div class="actions">
                        <button class="primary" id="pay-button" type="submit">Create JSAPI trade</button>
                        <button class="secondary" id="demo-button" type="button" hidden>Complete demo payment</button>
                        <button class="danger" id="refund-button" type="button" hidden>Refund order</button>
                    </div>
                    <div class="status" id="status">Selected: {{ $plans->first()->name }}</div>
                </form>

                <div class="summary" id="summary">
                    <h3>Order state</h3>
                    <div class="grid" id="summary-grid"></div>
                </div>
            @endif
        </div>
    </section>
</main>

<script>
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    const demoMode = @json($demoMode);
    const planInput = document.getElementById('plan-id');
    const statusEl = document.getElementById('status');
    const summaryEl = document.getElementById('summary');
    const summaryGrid = document.getElementById('summary-grid');
    const payButton = document.getElementById('pay-button');
    const demoButton = document.getElementById('demo-button');
    const refundButton = document.getElementById('refund-button');
    const form = document.getElementById('checkout-form');
    let currentOrder = null;

    document.querySelectorAll('.plan').forEach((button) => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.plan').forEach((item) => item.classList.remove('is-selected'));
            button.classList.add('is-selected');
            planInput.value = button.dataset.planId;
            statusEl.textContent = `Selected: ${button.dataset.planName}`;
        });
    });

    async function postJson(url, payload = {}) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'X-CSRF-TOKEN': csrfToken,
            },
            body: JSON.stringify(payload),
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.message || 'Request failed');
        }

        return data;
    }

    function setBusy(isBusy) {
        payButton.disabled = isBusy;
        demoButton.disabled = isBusy;
        refundButton.disabled = isBusy;
    }

    function renderOrder(order) {
        currentOrder = order;
        summaryEl.classList.add('is-visible');
        const statusClass = ['failed', 'refunded'].includes(order.status) ? order.status : '';
        const values = [
            ['Status', `<span class="state ${statusClass}">${order.status}</span>`],
            ['Amount', `¥${Number(order.amount || 0).toFixed(2)}`],
            ['out_trade_no', `<code>${order.out_trade_no || ''}</code>`],
            ['tradeNO', `<code>${order.tradeNO || ''}</code>`],
            ['Member', order.member ? `<code>${order.member.code} · ${order.member.name}</code>` : '<code>pending</code>'],
            ['Invoice', `<code>${order.invoice_id || 'pending'}</code>`],
            ['Subscription', `<code>${order.subscription_id || 'pending'}</code>`],
            ['Refund', `<code>${order.refund_amount || '0.00'}</code>`],
        ];

        summaryGrid.innerHTML = values.map(([label, value]) => `
            <div class="metric">
                <small>${label}</small>
                ${value}
            </div>
        `).join('');

        demoButton.hidden = !(demoMode && order.status === 'waiting_payment');
        refundButton.hidden = order.status !== 'paid';
    }

    async function syncOrder(order) {
        const data = await postJson(`/alipay-jsapi/orders/${order.out_trade_no}/sync`);
        renderOrder(data.order);
        statusEl.textContent = data.order.status === 'paid'
            ? 'Payment confirmed and membership created.'
            : `Alipay trade status: ${data.trade_status || data.order.status}`;
    }

    async function invokeTradePay(order) {
        if (!window.my || typeof window.my.tradePay !== 'function') {
            statusEl.textContent = demoMode
                ? 'Demo trade created. Complete the demo payment below.'
                : 'Open this checkout inside the Alipay mini program container.';
            return;
        }

        statusEl.textContent = 'Opening Alipay cashier...';
        window.my.tradePay({ tradeNO: order.tradeNO }, async (result) => {
            statusEl.textContent = `Alipay returned resultCode ${result.resultCode || 'unknown'}. Submitting client result...`;
            try {
                const data = await postJson(`/alipay-jsapi/orders/${order.out_trade_no}/client-result`, {
                    result_code: String(result.resultCode || ''),
                });
                renderOrder(data.order);
            } catch (error) {
                statusEl.textContent = error.message;
            }
        });
    }

    if (form) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            setBusy(true);
            statusEl.textContent = 'Creating Alipay JSAPI trade...';

            try {
                const payload = Object.fromEntries(new FormData(form).entries());
                const data = await postJson('/alipay-jsapi/orders', payload);
                renderOrder(data.order);
                await invokeTradePay(data.order);
            } catch (error) {
                statusEl.textContent = error.message;
            } finally {
                setBusy(false);
            }
        });

        demoButton.addEventListener('click', async () => {
            if (!currentOrder) {
                return;
            }

            setBusy(true);
            statusEl.textContent = 'Completing demo payment...';

            try {
                const data = await postJson(`/alipay-jsapi/orders/${currentOrder.out_trade_no}/demo-complete`);
                renderOrder(data.order);
                statusEl.textContent = 'Demo payment completed and membership created.';
            } catch (error) {
                statusEl.textContent = error.message;
            } finally {
                setBusy(false);
            }
        });

        refundButton.addEventListener('click', async () => {
            if (!currentOrder) {
                return;
            }

            setBusy(true);
            statusEl.textContent = 'Submitting refund...';

            try {
                const data = await postJson(`/alipay-jsapi/orders/${currentOrder.out_trade_no}/refund`, {
                    amount: currentOrder.amount,
                });
                renderOrder(data.order);
                statusEl.textContent = 'Refund recorded in invoice transactions.';
            } catch (error) {
                statusEl.textContent = error.message;
            } finally {
                setBusy(false);
            }
        });
    }
</script>
</body>
</html>
