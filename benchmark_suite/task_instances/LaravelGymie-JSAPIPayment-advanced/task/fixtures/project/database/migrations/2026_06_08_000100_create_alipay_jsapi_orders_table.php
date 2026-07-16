<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('alipay_jsapi_orders', function (Blueprint $table) {
            $table->id();
            $table->string('out_trade_no', 64)->unique();
            $table->string('trade_no')->nullable()->index();
            $table->foreignId('plan_id')->constrained()->cascadeOnDelete();
            $table->foreignId('member_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('subscription_id')->nullable()->constrained()->nullOnDelete();
            $table->foreignId('invoice_id')->nullable()->constrained()->nullOnDelete();
            $table->string('buyer_name');
            $table->string('buyer_email')->nullable();
            $table->string('buyer_contact')->nullable();
            $table->string('buyer_id')->nullable();
            $table->string('buyer_open_id')->nullable();
            $table->decimal('amount', 10, 2);
            $table->string('status')->default('created')->index();
            $table->timestamp('paid_at')->nullable();
            $table->timestamp('refunded_at')->nullable();
            $table->decimal('refund_amount', 10, 2)->default(0);
            $table->json('gateway_payload')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('alipay_jsapi_orders');
    }
};
