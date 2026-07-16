<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * @property int $id
 * @property string $out_trade_no
 * @property string|null $trade_no
 * @property int $plan_id
 * @property int|null $member_id
 * @property int|null $subscription_id
 * @property int|null $invoice_id
 * @property string $buyer_name
 * @property string|null $buyer_email
 * @property string|null $buyer_contact
 * @property string|null $buyer_id
 * @property string|null $buyer_open_id
 * @property string $amount
 * @property string $status
 * @property \Illuminate\Support\Carbon|null $paid_at
 * @property \Illuminate\Support\Carbon|null $refunded_at
 * @property string|null $refund_amount
 * @property array<string, mixed>|null $gateway_payload
 * @property-read Plan $plan
 * @property-read Member|null $member
 * @property-read Subscription|null $subscription
 * @property-read Invoice|null $invoice
 */
class AlipayJsapiOrder extends Model
{
    /** @use HasFactory<\Illuminate\Database\Eloquent\Factories\Factory<static>> */
    use HasFactory;

    public const STATUS_CREATED = 'created';
    public const STATUS_WAITING_PAYMENT = 'waiting_payment';
    public const STATUS_PAID = 'paid';
    public const STATUS_REFUNDED = 'refunded';
    public const STATUS_FAILED = 'failed';

    /**
     * @var list<string>
     */
    protected $fillable = [
        'out_trade_no',
        'trade_no',
        'plan_id',
        'member_id',
        'subscription_id',
        'invoice_id',
        'buyer_name',
        'buyer_email',
        'buyer_contact',
        'buyer_id',
        'buyer_open_id',
        'amount',
        'status',
        'paid_at',
        'refunded_at',
        'refund_amount',
        'gateway_payload',
    ];

    protected $casts = [
        'amount' => 'decimal:2',
        'refund_amount' => 'decimal:2',
        'paid_at' => 'datetime',
        'refunded_at' => 'datetime',
        'gateway_payload' => 'array',
    ];

    public function getRouteKeyName(): string
    {
        return 'out_trade_no';
    }

    /**
     * @return BelongsTo<Plan, $this>
     */
    public function plan(): BelongsTo
    {
        return $this->belongsTo(Plan::class);
    }

    /**
     * @return BelongsTo<Member, $this>
     */
    public function member(): BelongsTo
    {
        return $this->belongsTo(Member::class);
    }

    /**
     * @return BelongsTo<Subscription, $this>
     */
    public function subscription(): BelongsTo
    {
        return $this->belongsTo(Subscription::class);
    }

    /**
     * @return BelongsTo<Invoice, $this>
     */
    public function invoice(): BelongsTo
    {
        return $this->belongsTo(Invoice::class);
    }
}
