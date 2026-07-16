<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * @property int $id
 * @property int|null $invoice_id
 * @property string $type
 * @property float|int|string|null $amount
 * @property \Illuminate\Support\Carbon|null $occurred_at
 * @property string|null $payment_method
 * @property string|null $note
 * @property string|null $reference_id
 * @property int|null $created_by
 * @property-read Invoice|null $invoice
 */
class InvoiceTransaction extends Model
{
    /** @use HasFactory<\Illuminate\Database\Eloquent\Factories\Factory<static>> */
    use HasFactory;

    /**
     * @var list<string>
     */
    protected $fillable = [
        'invoice_id',
        'type',
        'amount',
        'occurred_at',
        'payment_method',
        'note',
        'reference_id',
        'created_by',
    ];

    protected $casts = [
        'occurred_at' => 'datetime',
    ];

    /**
     * Get the invoice that this transaction belongs to.
     *
     * @return BelongsTo<Invoice, $this>
     */
    public function invoice(): BelongsTo
    {
        return $this->belongsTo(Invoice::class);
    }

    /**
     * The "booted" method of the model.
     */
    protected static function booted(): void
    {
        static::saved(function (self $transaction): void {
            if ($transaction->invoice instanceof Invoice) {
                $transaction->invoice->syncFromTransactions();
            }
        });

        static::deleted(function (self $transaction): void {
            if ($transaction->invoice instanceof Invoice) {
                $transaction->invoice->syncFromTransactions();
            }
        });
    }
}
