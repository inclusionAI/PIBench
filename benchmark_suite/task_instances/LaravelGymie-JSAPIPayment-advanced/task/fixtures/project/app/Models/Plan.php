<?php

namespace App\Models;

use App\Enums\Status;
use App\Models\Concerns\CascadesSoftDeletes;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * @property int $id
 * @property string $name
 * @property string $code
 * @property string|null $description
 * @property int|null $service_id
 * @property float|int|string|null $amount
 * @property int|float|string|null $days
 * @property Status|null $status
 * @property-read Service|null $service
 * @property-read \Illuminate\Database\Eloquent\Collection<int, Subscription> $subscriptions
 */
class Plan extends Model
{
    /** @use HasFactory<\Database\Factories\PlanFactory> */
    use CascadesSoftDeletes, HasFactory, SoftDeletes;

    /**
     * The attributes that are mass assignable.
     *
     * @var list<string>
     */
    protected $fillable = [
        'name',
        'code',
        'description',
        'service_id',
        'amount',
        'days',
        'status',
    ];

    protected $casts = [
        'status' => Status::class,
    ];

    /** @var list<string> */
    protected $dates = ['deleted_at'];

    /**
     * Get the sevice for the plan.
     */
    /**
     * @return BelongsTo<Service, $this>
     */
    public function service(): BelongsTo
    {
        return $this->belongsTo(Service::class);
    }

    /**
     * Get the subscriptions for the plan.
     */
    /**
     * @return HasMany<Subscription, $this>
     */
    public function subscriptions(): HasMany
    {
        return $this->hasMany(Subscription::class);
    }

    /**
     * Relationship method names to cascade when deleting/restoring.
     *
     * @return list<string>
     */
    protected static function relationsToCascade(): array
    {
        return ['subscriptions'];
    }
}
