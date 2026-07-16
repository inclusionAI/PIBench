<?php

namespace App\Models;

use App\Enums\Status;
use Database\Factories\FollowUpFactory;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * @property int $id
 * @property int|null $enquiry_id
 * @property int|null $user_id
 * @property \Illuminate\Support\Carbon|null $schedule_date
 * @property string|null $method
 * @property string|null $outcome
 * @property Status|null $status
 * @property-read Enquiry|null $enquiry
 * @property-read User|null $user
 */
class FollowUp extends Model
{
    /** @use HasFactory<FollowUpFactory> */
    use HasFactory, SoftDeletes;

    /**
     * The attributes that are mass assignable.
     *
     * @var list<string>
     */
    protected $fillable = [
        'enquiry_id',
        'user_id',
        'schedule_date',
        'method',
        'outcome',
        'status',
    ];

    protected $casts = [
        'schedule_date' => 'date',
        'status' => Status::class,
    ];

    /** @var list<string> */
    protected $dates = ['deleted_at'];

    /**
     * Get the enquiry for the follow-up.
     */
    /**
     * @return BelongsTo<Enquiry, $this>
     */
    public function enquiry(): BelongsTo
    {
        return $this->belongsTo(Enquiry::class);
    }

    /**
     * Get the user for the follow-up.
     */
    /**
     * @return BelongsTo<User, $this>
     */
    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }
}
