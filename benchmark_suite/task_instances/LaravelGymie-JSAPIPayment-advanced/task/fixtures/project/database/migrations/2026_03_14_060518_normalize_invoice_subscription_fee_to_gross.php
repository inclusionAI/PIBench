<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    private const EPSILON = 0.01;

    /**
     * Run the migrations.
     */
    public function up(): void
    {
        DB::table('invoices')
            ->whereRaw('COALESCE(discount_amount, 0) > 0')
            ->whereRaw(
                'ABS((COALESCE(subscription_fee, 0) + COALESCE(tax, 0)) - COALESCE(total_amount, 0)) < ?',
                [self::EPSILON],
            )
            ->update([
                'subscription_fee' => DB::raw('COALESCE(subscription_fee, 0) + COALESCE(discount_amount, 0)'),
            ]);
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        DB::table('invoices')
            ->whereRaw('COALESCE(discount_amount, 0) > 0')
            ->whereRaw(
                'ABS((COALESCE(subscription_fee, 0) + COALESCE(tax, 0) - COALESCE(discount_amount, 0)) - COALESCE(total_amount, 0)) < ?',
                [self::EPSILON],
            )
            ->update([
                'subscription_fee' => DB::raw('COALESCE(subscription_fee, 0) - COALESCE(discount_amount, 0)'),
            ]);
    }
};
