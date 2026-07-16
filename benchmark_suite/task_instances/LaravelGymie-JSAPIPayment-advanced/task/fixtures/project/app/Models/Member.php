<?php

namespace App\Models;

use App\Enums\Status;
use App\Helpers\Helpers;
use App\Models\Concerns\CascadesSoftDeletes;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * @property int $id
 * @property string|null $photo
 * @property string $code
 * @property string $name
 * @property string|null $email
 * @property string|null $contact
 * @property string|null $emergency_contact
 * @property string|null $health_issue
 * @property string|null $gender
 * @property \Illuminate\Support\Carbon|null $dob
 * @property string|null $address
 * @property string|null $country
 * @property string|null $state
 * @property string|null $city
 * @property string|null $pincode
 * @property string|null $source
 * @property string|null $goal
 * @property Status|null $status
 * @property-read \Illuminate\Database\Eloquent\Collection<int, Subscription> $subscriptions
 */
class Member extends Model
{
    /** @use HasFactory<\Database\Factories\MemberFactory> */
    use CascadesSoftDeletes, HasFactory, SoftDeletes;

    /**
     * The attributes that are mass assignable.
     *
     * @var list<string>
     */
    protected $fillable = [
        'photo',
        'code',
        'name',
        'email',
        'contact',
        'emergency_contact',
        'health_issue',
        'gender',
        'dob',
        'address',
        'country',
        'state',
        'city',
        'pincode',
        'source',
        'goal',
        'status',
    ];

    protected $casts = ['dob' => 'date', 'status' => Status::class];

    /**
     * The attributes that should be mutated to dates.
     * (SoftDeletes already adds deleted_at rollover.)
     *
     * @var list<string>
     */
    protected $dates = [
        'dob',
        'deleted_at',
    ];

    /**
     * Get the subscriptions for the member.
     */
    /**
     * @return HasMany<Subscription, $this>
     */
    public function subscriptions(): HasMany
    {
        return $this->hasMany(Subscription::class);
    }

    /**
     * Boot the model and add cascade delete and restore behavior.
     */
    protected static function boot(): void
    {
        parent::boot();

        static::saving(function (self $member): void {
            if (! $member->code) {
                $member->code = Helpers::generateLastNumber('member', Member::class, null, 'code');
            }
            Helpers::updateLastNumber('member', $member->code);
        });
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
