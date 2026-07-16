<?php

namespace App\Services\Alipay;

use App\Helpers\Helpers;
use App\Models\AlipayJsapiOrder;
use App\Models\Invoice;
use App\Models\InvoiceTransaction;
use App\Models\Member;
use App\Models\Subscription;
use App\Support\AppConfig;
use Carbon\Carbon;
use Illuminate\Support\Facades\DB;

class AlipayMembershipFulfillmentService
{
    /**
     * @param  array<string, mixed>  $gatewayPayload
     */
    public function markPaid(AlipayJsapiOrder $order, ?string $tradeNo, array $gatewayPayload, string $source): AlipayJsapiOrder
    {
        return DB::transaction(function () use ($order, $tradeNo, $gatewayPayload, $source): AlipayJsapiOrder {
            $order = $order->lockForUpdate()->findOrFail($order->id);

            if ($order->status === AlipayJsapiOrder::STATUS_PAID || $order->status === AlipayJsapiOrder::STATUS_REFUNDED) {
                return $order->refresh();
            }

            $plan = $order->plan()->lockForUpdate()->firstOrFail();
            $today = Carbon::today(AppConfig::timezone())->toDateString();
            $endDate = Helpers::calculateSubscriptionEndDate($today, (int) $plan->id) ?: Carbon::parse($today)->addDays(30)->toDateString();

            $member = $this->memberForOrder($order);

            $subscription = Subscription::create([
                'member_id' => $member->id,
                'plan_id' => $plan->id,
                'start_date' => $today,
                'end_date' => $endDate,
                'status' => 'ongoing',
            ]);

            $invoice = Invoice::create([
                'subscription_id' => $subscription->id,
                'date' => $today,
                'due_date' => $today,
                'payment_method' => 'alipay_jsapi',
                'paid_amount' => 0,
                'subscription_fee' => (float) $order->amount,
                'status' => 'issued',
            ]);

            InvoiceTransaction::create([
                'invoice_id' => $invoice->id,
                'type' => 'payment',
                'amount' => (float) $order->amount,
                'occurred_at' => now(AppConfig::timezone()),
                'payment_method' => 'alipay_jsapi',
                'note' => 'Alipay JSAPI payment via '.$source,
                'reference_id' => $tradeNo ?: $order->trade_no ?: $order->out_trade_no,
            ]);

            $order->update([
                'member_id' => $member->id,
                'subscription_id' => $subscription->id,
                'invoice_id' => $invoice->id,
                'trade_no' => $tradeNo ?: $order->trade_no,
                'status' => AlipayJsapiOrder::STATUS_PAID,
                'paid_at' => now(AppConfig::timezone()),
                'gateway_payload' => $gatewayPayload,
            ]);

            return $order->refresh()->load(['plan', 'member', 'subscription', 'invoice']);
        });
    }

    /**
     * @param  array<string, mixed>  $gatewayPayload
     */
    public function markRefunded(AlipayJsapiOrder $order, float $amount, string $referenceId, array $gatewayPayload): AlipayJsapiOrder
    {
        return DB::transaction(function () use ($order, $amount, $referenceId, $gatewayPayload): AlipayJsapiOrder {
            $order = $order->lockForUpdate()->findOrFail($order->id);

            if (! $order->invoice_id || $order->status === AlipayJsapiOrder::STATUS_REFUNDED) {
                return $order->refresh();
            }

            $invoice = Invoice::query()->lockForUpdate()->findOrFail($order->invoice_id);

            InvoiceTransaction::create([
                'invoice_id' => $invoice->id,
                'type' => 'refund',
                'amount' => min($amount, (float) $invoice->paid_amount),
                'occurred_at' => now(AppConfig::timezone()),
                'payment_method' => 'alipay_jsapi',
                'note' => 'Alipay JSAPI refund',
                'reference_id' => $referenceId,
            ]);

            $order->update([
                'status' => AlipayJsapiOrder::STATUS_REFUNDED,
                'refunded_at' => now(AppConfig::timezone()),
                'refund_amount' => min($amount, (float) $order->amount),
                'gateway_payload' => [
                    ...($order->gateway_payload ?? []),
                    'refund' => $gatewayPayload,
                ],
            ]);

            return $order->refresh()->load(['plan', 'member', 'subscription', 'invoice']);
        });
    }

    private function memberForOrder(AlipayJsapiOrder $order): Member
    {
        if ($order->buyer_email) {
            $member = Member::query()->where('email', $order->buyer_email)->first();
            if ($member) {
                $member->update([
                    'name' => $order->buyer_name,
                    'contact' => $order->buyer_contact ?: $member->contact,
                    'status' => 'active',
                ]);

                return $member->refresh();
            }
        }

        return Member::create([
            'name' => $order->buyer_name,
            'email' => $order->buyer_email,
            'contact' => $order->buyer_contact,
            'source' => 'alipay_jsapi',
            'goal' => 'fitness',
            'status' => 'active',
        ]);
    }
}
