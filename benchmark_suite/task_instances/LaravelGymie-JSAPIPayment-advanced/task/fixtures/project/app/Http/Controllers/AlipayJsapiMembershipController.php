<?php

namespace App\Http\Controllers;

use App\Models\AlipayJsapiOrder;
use App\Models\Plan;
use App\Services\Alipay\AlipayJsapiPaymentService;
use App\Services\Alipay\AlipayMembershipFulfillmentService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Illuminate\View\View;
use Throwable;

class AlipayJsapiMembershipController extends Controller
{
    public function index(AlipayJsapiPaymentService $payments): View
    {
        return view('alipay-jsapi.memberships', [
            'plans' => $this->membershipPlans(),
            'demoMode' => $payments->isDemoMode(),
        ]);
    }

    public function plans(AlipayJsapiPaymentService $payments): JsonResponse
    {
        return response()->json([
            'demo_mode' => $payments->isDemoMode(),
            'plans' => $this->membershipPlans()
                ->map(fn (Plan $plan): array => [
                    'id' => $plan->id,
                    'code' => $plan->code,
                    'name' => $plan->name,
                    'description' => $plan->description,
                    'days' => $plan->days,
                    'amount' => number_format((float) $plan->amount, 2, '.', ''),
                ])
                ->values(),
        ]);
    }

    public function store(Request $request, AlipayJsapiPaymentService $payments): JsonResponse
    {
        $data = $request->validate([
            'plan_id' => ['required', 'integer', 'exists:plans,id'],
            'buyer_name' => ['required', 'string', 'max:120'],
            'buyer_email' => ['nullable', 'email', 'max:190'],
            'buyer_contact' => ['nullable', 'string', 'max:60'],
            'buyer_id' => ['nullable', 'string', 'max:120'],
            'buyer_open_id' => ['nullable', 'string', 'max:120'],
            'buyer_auth_code' => ['nullable', 'string', 'max:120'],
        ]);

        if (! $payments->isDemoMode()
            && empty($data['buyer_id'])
            && empty($data['buyer_open_id'])
            && ! empty($data['buyer_auth_code'])
        ) {
            try {
                $identity = $payments->exchangeAuthCode($data['buyer_auth_code']);
                $data['buyer_id'] = $identity['user_id'] ?: null;
                $data['buyer_open_id'] = $identity['open_id'] ?: null;
            } catch (Throwable $exception) {
                return response()->json(['message' => $exception->getMessage()], 422);
            }
        }

        if (! $payments->isDemoMode() && empty($data['buyer_id']) && empty($data['buyer_open_id'])) {
            return response()->json([
                'message' => 'buyer_id, buyer_open_id, or buyer_auth_code is required for real Alipay JSAPI mode.',
            ], 422);
        }

        $plan = Plan::query()->findOrFail($data['plan_id']);

        $order = AlipayJsapiOrder::create([
            'out_trade_no' => $this->makeOutTradeNo(),
            'plan_id' => $plan->id,
            'buyer_name' => $data['buyer_name'],
            'buyer_email' => $data['buyer_email'] ?? null,
            'buyer_contact' => $data['buyer_contact'] ?? null,
            'buyer_id' => $data['buyer_id'] ?? null,
            'buyer_open_id' => $data['buyer_open_id'] ?? null,
            'amount' => number_format((float) $plan->amount, 2, '.', ''),
            'status' => AlipayJsapiOrder::STATUS_CREATED,
        ])->load('plan');

        try {
            $trade = $payments->createTrade($order);
            $order->update([
                'trade_no' => $trade['trade_no'],
                'status' => AlipayJsapiOrder::STATUS_WAITING_PAYMENT,
                'gateway_payload' => $trade['response'],
            ]);
        } catch (Throwable $exception) {
            $order->update([
                'status' => AlipayJsapiOrder::STATUS_FAILED,
                'gateway_payload' => ['error' => $exception->getMessage()],
            ]);

            return response()->json([
                'message' => $exception->getMessage(),
                'order' => $this->payload($order->refresh()),
            ], 422);
        }

        return response()->json([
            'message' => 'Alipay JSAPI trade created.',
            'demo_mode' => $payments->isDemoMode(),
            'order' => $this->payload($order->refresh()->load(['plan', 'member', 'subscription', 'invoice'])),
        ]);
    }

    public function status(AlipayJsapiOrder $order): JsonResponse
    {
        return response()->json([
            'order' => $this->payload($order->load(['plan', 'member', 'subscription', 'invoice'])),
        ]);
    }

    public function sync(AlipayJsapiOrder $order): JsonResponse
    {
        return response()->json([
            'trade_status' => $order->status,
            'message' => 'TODO: query Alipay when notify is missing instead of trusting local state.',
            'order' => $this->payload($order->load(['plan', 'member', 'subscription', 'invoice'])),
        ]);
    }

    public function clientResult(
        Request $request,
        AlipayJsapiOrder $order,
        AlipayMembershipFulfillmentService $fulfillment,
    ): JsonResponse {
        $data = $request->validate([
            'result_code' => ['required', 'string', 'max:20'],
        ]);

        $resultCode = (string) $data['result_code'];

        if ($resultCode === '9000') {
            $order = $fulfillment->markPaid($order, $order->trade_no, [
                'source' => 'miniapp_client_result',
                'result_code' => $resultCode,
                'out_trade_no' => $order->out_trade_no,
            ], 'miniapp_client_result');
        } elseif (in_array($resultCode, ['4000', '6001', '6002'], true)) {
            $order->update([
                'status' => AlipayJsapiOrder::STATUS_FAILED,
                'gateway_payload' => [
                    ...($order->gateway_payload ?? []),
                    'client_result' => [
                        'result_code' => $resultCode,
                    ],
                ],
            ]);
        }

        return response()->json([
            'message' => 'Client result accepted without payment-provider confirmation.',
            'order' => $this->payload($order->refresh()->load(['plan', 'member', 'subscription', 'invoice'])),
        ]);
    }

    public function completeDemo(
        AlipayJsapiOrder $order,
        AlipayJsapiPaymentService $payments,
        AlipayMembershipFulfillmentService $fulfillment,
    ): JsonResponse {
        if (! $payments->isDemoMode()) {
            return response()->json(['message' => 'Demo completion is disabled in real Alipay mode.'], 403);
        }

        $order = $fulfillment->markPaid($order, $order->trade_no, [
            'code' => 'DEMO',
            'trade_status' => 'TRADE_SUCCESS',
            'out_trade_no' => $order->out_trade_no,
            'total_amount' => (string) $order->amount,
        ], 'demo');

        return response()->json([
            'message' => 'Demo payment completed.',
            'order' => $this->payload($order),
        ]);
    }

    public function notify(
        Request $request,
        AlipayJsapiPaymentService $payments,
        AlipayMembershipFulfillmentService $fulfillment,
    ): \Illuminate\Http\Response {
        $payload = $request->all();

        $order = AlipayJsapiOrder::query()
            ->where('out_trade_no', (string) ($payload['out_trade_no'] ?? ''))
            ->first();

        if (! $order) {
            return response('fail', 400);
        }

        if ($this->tradeIsPaid($payload)) {
            $fulfillment->markPaid(
                $order,
                (string) ($payload['trade_no'] ?? $order->trade_no),
                $payload,
                'alipay_notify'
            );
        }

        return response('success');
    }

    public function refund(
        Request $request,
        AlipayJsapiOrder $order,
        AlipayJsapiPaymentService $payments,
        AlipayMembershipFulfillmentService $fulfillment,
    ): JsonResponse {
        $this->guardRefundToken($request);

        if ($order->status !== AlipayJsapiOrder::STATUS_PAID) {
            return response()->json(['message' => 'Only paid orders can be refunded.'], 409);
        }

        $data = $request->validate([
            'amount' => ['nullable', 'numeric', 'min:0.01'],
        ]);

        $amount = min((float) ($data['amount'] ?? $order->amount), (float) $order->amount);
        $refundRequestNo = 'RF'.now()->format('YmdHis').strtoupper(Str::random(8));

        try {
            $refund = $payments->refund($order, $amount, $refundRequestNo);
        } catch (Throwable $exception) {
            return response()->json(['message' => $exception->getMessage()], 422);
        }

        $order = $fulfillment->markRefunded($order, $amount, $refundRequestNo, $refund);

        return response()->json([
            'message' => 'Alipay JSAPI refund recorded.',
            'refund' => $refund,
            'order' => $this->payload($order),
        ]);
    }

    private function makeOutTradeNo(): string
    {
        return 'GYMJSAPI'.now()->format('YmdHis').strtoupper(Str::random(10));
    }

    private function membershipPlans()
    {
        $plans = Plan::query()
            ->where('status', 'active')
            ->whereNotNull('amount')
            ->where('amount', '>', 0)
            ->orderBy('amount')
            ->get();

        if ($plans->isNotEmpty()) {
            return $plans;
        }

        return Plan::query()
            ->whereNotNull('amount')
            ->where('amount', '>', 0)
            ->orderBy('amount')
            ->limit(6)
            ->get();
    }

    /**
     * @param  array<string, mixed>  $trade
     */
    private function tradeIsPaid(array $trade): bool
    {
        return in_array((string) ($trade['trade_status'] ?? ''), ['TRADE_SUCCESS', 'TRADE_FINISHED'], true);
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function amountMatches(AlipayJsapiOrder $order, array $payload): bool
    {
        if (! isset($payload['total_amount'])) {
            return true;
        }

        return abs((float) $payload['total_amount'] - (float) $order->amount) < 0.01;
    }

    /**
     * @param  array<string, mixed>  $payload
     */
    private function sellerMatches(array $payload): bool
    {
        $sellerId = (string) config('services.alipay_jsapi.seller_id');

        return $sellerId === '' || (string) ($payload['seller_id'] ?? '') === $sellerId;
    }

    private function guardRefundToken(Request $request): void
    {
        $token = (string) config('services.alipay_jsapi.refund_token');
        if ($token === '') {
            return;
        }

        abort_unless(
            hash_equals($token, (string) ($request->header('X-Refund-Token') ?: $request->input('token'))),
            403
        );
    }

    /**
     * @return array<string, mixed>
     */
    private function payload(AlipayJsapiOrder $order): array
    {
        return [
            'out_trade_no' => $order->out_trade_no,
            'tradeNO' => $order->trade_no,
            'trade_no' => $order->trade_no,
            'status' => $order->status,
            'amount' => (string) $order->amount,
            'paid_at' => $order->paid_at?->toIso8601String(),
            'refunded_at' => $order->refunded_at?->toIso8601String(),
            'refund_amount' => (string) $order->refund_amount,
            'plan' => $order->plan ? [
                'id' => $order->plan->id,
                'name' => $order->plan->name,
                'days' => $order->plan->days,
                'amount' => (string) $order->plan->amount,
            ] : null,
            'member' => $order->member ? [
                'id' => $order->member->id,
                'code' => $order->member->code,
                'name' => $order->member->name,
                'email' => $order->member->email,
            ] : null,
            'subscription_id' => $order->subscription_id,
            'invoice_id' => $order->invoice_id,
        ];
    }
}
