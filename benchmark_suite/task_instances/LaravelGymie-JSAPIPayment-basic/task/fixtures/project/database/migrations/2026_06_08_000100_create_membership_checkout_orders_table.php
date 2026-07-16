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
        Schema::create('membership_checkout_orders', function (Blueprint $table) {
            $table->id();
            $table->string('checkout_no', 64)->unique();
            $table->foreignId('plan_id')->constrained()->cascadeOnDelete();
            $table->string('buyer_name');
            $table->string('buyer_email')->nullable();
            $table->string('buyer_contact')->nullable();
            $table->decimal('amount', 10, 2);
            $table->string('status')->default('created')->index();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('membership_checkout_orders');
    }
};
