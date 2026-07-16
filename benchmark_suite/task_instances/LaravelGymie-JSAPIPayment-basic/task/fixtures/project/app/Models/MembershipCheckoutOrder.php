<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * @property int $id
 * @property string $checkout_no
 * @property int $plan_id
 * @property string $buyer_name
 * @property string|null $buyer_email
 * @property string|null $buyer_contact
 * @property string $amount
 * @property string $status
 * @property-read Plan $plan
 */
class MembershipCheckoutOrder extends Model
{
    /** @use HasFactory<\Illuminate\Database\Eloquent\Factories\Factory<static>> */
    use HasFactory;

    public const STATUS_CREATED = 'created';

    /**
     * @var list<string>
     */
    protected $fillable = [
        'checkout_no',
        'plan_id',
        'buyer_name',
        'buyer_email',
        'buyer_contact',
        'amount',
        'status',
    ];

    protected $casts = [
        'amount' => 'decimal:2',
    ];

    public function getRouteKeyName(): string
    {
        return 'checkout_no';
    }

    /**
     * @return BelongsTo<Plan, $this>
     */
    public function plan(): BelongsTo
    {
        return $this->belongsTo(Plan::class);
    }
}
