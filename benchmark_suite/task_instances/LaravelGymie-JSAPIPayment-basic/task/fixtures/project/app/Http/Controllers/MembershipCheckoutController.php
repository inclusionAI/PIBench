<?php

namespace App\Http\Controllers;

use App\Models\MembershipCheckoutOrder;
use App\Models\Plan;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Str;
use Illuminate\View\View;

class MembershipCheckoutController extends Controller
{
    public function index(): View
    {
        return view('membership-checkout.index', [
            'plans' => $this->membershipPlans(),
        ]);
    }

    public function plans(): JsonResponse
    {
        return response()->json([
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

    public function store(Request $request): JsonResponse
    {
        $data = $request->validate([
            'plan_id' => ['required', 'integer', 'exists:plans,id'],
            'buyer_name' => ['required', 'string', 'max:120'],
            'buyer_email' => ['nullable', 'email', 'max:190'],
            'buyer_contact' => ['nullable', 'string', 'max:60'],
        ]);

        $plan = Plan::query()->findOrFail($data['plan_id']);

        $order = MembershipCheckoutOrder::create([
            'checkout_no' => $this->makeCheckoutNo(),
            'plan_id' => $plan->id,
            'buyer_name' => $data['buyer_name'],
            'buyer_email' => $data['buyer_email'] ?? null,
            'buyer_contact' => $data['buyer_contact'] ?? null,
            'amount' => number_format((float) $plan->amount, 2, '.', ''),
            'status' => MembershipCheckoutOrder::STATUS_CREATED,
        ])->load('plan');

        return response()->json([
            'message' => 'Membership order created.',
            'order' => $this->payload($order),
        ], 201);
    }

    public function status(MembershipCheckoutOrder $order): JsonResponse
    {
        return response()->json([
            'order' => $this->payload($order->load('plan')),
        ]);
    }

    private function makeCheckoutNo(): string
    {
        return 'GYM'.now()->format('YmdHis').strtoupper(Str::random(10));
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
     * @return array<string, mixed>
     */
    private function payload(MembershipCheckoutOrder $order): array
    {
        return [
            'checkout_no' => $order->checkout_no,
            'status' => $order->status,
            'amount' => (string) $order->amount,
            'buyer' => [
                'name' => $order->buyer_name,
                'email' => $order->buyer_email,
                'contact' => $order->buyer_contact,
            ],
            'plan' => $order->plan ? [
                'id' => $order->plan->id,
                'name' => $order->plan->name,
                'days' => $order->plan->days,
                'amount' => (string) $order->plan->amount,
            ] : null,
            'created_at' => $order->created_at?->toIso8601String(),
        ];
    }
}
