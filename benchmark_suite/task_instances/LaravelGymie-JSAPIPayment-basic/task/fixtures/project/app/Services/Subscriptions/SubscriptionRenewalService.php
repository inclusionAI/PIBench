<?php

namespace App\Services\Subscriptions;

use App\Helpers\Helpers;
use App\Models\Invoice;
use App\Models\Plan;
use App\Models\Subscription;
use App\Support\Billing\PaymentMethod;
use App\Support\Data;
use Carbon\Carbon;

/**
 * Subscription renewal domain service.
 *
 * This is extracted from Filament-only flows so the same logic can be reused by
 * the JSON API and other integrations without depending on UI classes.
 */
class SubscriptionRenewalService
{
    /**
     * Renew a subscription and generate an associated invoice.
     *
     * The created invoice is always issued. If the chosen payment method is
     * online, we force `paid_amount=0` and rely on the payment ledger / webhooks
     * to update invoice status.
     *
     * @param  array{
     *   plan_id:int,
     *   start_date:string,
     *   end_date?:string|null,
     *   invoice?:array{
     *     number?:string|null,
     *     date?:string|null,
     *     due_date?:string|null,
     *     payment_method?:string|null,
     *     discount?:int|float|string|null,
     *     discount_amount?:float|int|string|null,
     *     discount_note?:string|null,
     *     paid_amount?:float|int|string|null
     *   }
     * }  $data
     * @return array{subscription: Subscription, invoice: Invoice}
     */
    public function renew(Subscription $record, array $data): array
    {
        /** @var array{subscription: Subscription, invoice: Invoice} $result */
        $result = Subscription::query()->getConnection()->transaction(function () use ($record, $data): array {
            $timezone = \App\Support\AppConfig::timezone();
            $today = Carbon::today($timezone);

            $plan = Plan::findOrFail(Data::int($data['plan_id']));

            $startDate = Carbon::parse(Data::string($data['start_date']))->toDateString();
            $endDate = Data::string($data['end_date'] ?? null) ?: Helpers::calculateSubscriptionEndDate($startDate, Data::int($plan->id));
            $endDate = Carbon::parse($endDate)->toDateString();

            $status = Carbon::parse($startDate)->gt($today)
                ? 'upcoming'
                : 'ongoing';

            $newSubscription = Subscription::create([
                'renewed_from_subscription_id' => $record->id,
                'member_id' => $record->member_id,
                'plan_id' => $plan->id,
                'start_date' => $startDate,
                'end_date' => $endDate,
                'status' => $status,
            ]);

            if ($record->end_date && $record->end_date->lt($today)) {
                $record->update([
                    'status' => 'renewed',
                ]);
            }

            $invoiceData = $data['invoice'] ?? [];

            $fee = round(Data::float($plan->amount), 2);

            $discountPct = max(Data::int($invoiceData['discount'] ?? 0), 0);
            $discountAmount = Data::float($invoiceData['discount_amount'] ?? 0);
            $discountAmount = min(max($discountAmount, 0), $fee);
            if ($discountPct > 0 && $discountAmount <= 0) {
                $discountAmount = (float) Helpers::getDiscountAmount($discountPct, $fee);
            }

            $paymentMethod = Data::nullableString($invoiceData['payment_method'] ?? null);
            $paidAmount = max(Data::float($invoiceData['paid_amount'] ?? 0), 0);

            if (PaymentMethod::isOnline($paymentMethod)) {
                $paidAmount = 0;
            }

            $invoiceDate = Carbon::parse(Data::string($invoiceData['date'] ?? $startDate))->toDateString();
            $invoiceDueDate = Carbon::parse(Data::string($invoiceData['due_date'] ?? $invoiceDate))->toDateString();

            $invoice = Invoice::create([
                'number' => $invoiceData['number'] ?? null,
                'subscription_id' => $newSubscription->id,
                'date' => $invoiceDate,
                'due_date' => $invoiceDueDate,
                'payment_method' => $paymentMethod,
                'discount' => $discountPct ?: null,
                'discount_amount' => $discountAmount ?: null,
                'discount_note' => $invoiceData['discount_note'] ?? null,
                'paid_amount' => $paidAmount,
                'subscription_fee' => $fee,
                'status' => 'issued',
            ]);

            return [
                'subscription' => $newSubscription->refresh(),
                'invoice' => $invoice->refresh(),
            ];
        });

        return $result;
    }
}
