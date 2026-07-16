<?php

namespace App\Models;

use App\Enums\Status;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * @property int $id
 * @property int|null $renewed_from_subscription_id
 * @property int|null $member_id
 * @property int|null $plan_id
 * @property \Illuminate\Support\Carbon|null $start_date
 * @property \Illuminate\Support\Carbon|null $end_date
 * @property Status|null $status
 * @property-read Member|null $member
 * @property-read Plan|null $plan
 * @property-read Subscription|null $renewedFrom
 * @property-read \Illuminate\Database\Eloquent\Collection<int, Subscription> $renewals
 * @property-read \Illuminate\Database\Eloquent\Collection<int, Invoice> $invoices
 */
class Subscription extends Model
{
    /** @use HasFactory<\Database\Factories\SubscriptionFactory> */
    use HasFactory, SoftDeletes;

    /**
     * The attributes that are mass assignable.
     *
     * @var list<string>
     */
    protected $fillable = [
        'renewed_from_subscription_id',
        'member_id',
        'plan_id',
        'start_date',
        'end_date',
        'status',
    ];

    protected $casts = [
        'start_date' => 'date',
        'end_date' => 'date',
        'status' => Status::class,
    ];

    /** @var list<string> */
    protected $dates = ['deleted_at', 'start_date', 'end_date'];

    /**
     * Get the invoices for the subscription.
     */
    /**
     * @return HasMany<Invoice, $this>
     */
    public function invoices(): HasMany
    {
        return $this->hasMany(Invoice::class);
    }

    /**
     * Get the subscription that this subscription was renewed from, if any.
     *
     * @return BelongsTo<Subscription, $this>
     */
    public function renewedFrom(): BelongsTo
    {
        return $this->belongsTo(self::class, 'renewed_from_subscription_id');
    }

    /**
     * Get the subscriptions that were renewed from this subscription.
     *
     * @return HasMany<Subscription, $this>
     */
    public function renewals(): HasMany
    {
        return $this->hasMany(self::class, 'renewed_from_subscription_id');
    }

    /**
     * The member who owns this subscription.
     */
    /**
     * @return BelongsTo<Member, $this>
     */
    public function member(): BelongsTo
    {
        return $this->belongsTo(Member::class);
    }

    /**
     * The plan this subscription is for.
     */
    /**
     * @return BelongsTo<Plan, $this>
     */
    public function plan(): BelongsTo
    {
        return $this->belongsTo(Plan::class);
    }
}
