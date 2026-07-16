<?php

namespace Database\Factories;

use App\Helpers\Helpers;
use App\Models\Subscription;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends \Illuminate\Database\Eloquent\Factories\Factory<\App\Models\Invoice>
 */
class InvoiceFactory extends Factory
{
    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        // Create or fetch a subscription (and its plan & member)
        $subscription = Subscription::factory();

        // Dates
        $date = $this->faker->dateTimeBetween('-1 year', 'now');
        $dueDate = (clone $date)->modify('+30 days');

        // Fee
        $fee = $this->faker->randomFloat(2, 50, 1000);

        // Discount
        $discountOptions = array_keys(Helpers::getDiscounts());
        $discountPct = $this->faker->randomElement($discountOptions);
        $discountAmount = round(Helpers::getDiscountAmount($discountPct, $fee), 2);

        // Payments (clamped by the model on save)
        $paidAmount = $this->faker->randomFloat(2, 0, $fee);

        return [
            'number' => $this->faker->unique()->numerify('INV-#####'),
            'subscription_id' => $subscription,
            'date' => $date,
            'due_date' => $dueDate,
            'payment_method' => $this->faker->randomElement(['offline', 'stripe']),
            'status' => 'issued',
            'subscription_fee' => $fee,
            'discount' => $discountPct,
            'discount_amount' => $discountAmount,
            'discount_note' => $this->faker->sentence(3),
            'paid_amount' => $paidAmount,
        ];
    }
}
