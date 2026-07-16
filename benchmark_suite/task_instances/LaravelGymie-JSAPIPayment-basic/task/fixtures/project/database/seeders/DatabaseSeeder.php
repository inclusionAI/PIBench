<?php

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use Nnjeim\World\Actions\SeedAction;

class DatabaseSeeder extends Seeder
{
    /**
     * Seed the application's database.
     */
    public function run(): void
    {
        if (! class_exists(\Faker\Factory::class)) {
            $this->call([
                SeedAction::class,
                ShieldSeeder::class,
                UserSeeder::class,
                MembershipCheckoutDemoSeeder::class,
            ]);

            return;
        }

        $this->call([
            SeedAction::class,
            ShieldSeeder::class,
            UserSeeder::class,
            ServiceSeeder::class,
            PlanSeeder::class,
            MembershipCheckoutDemoSeeder::class,
            EnquirySeeder::class,
            FollowUpSeeder::class,
            MemberSeeder::class,
            SubscriptionSeeder::class,
            InvoiceSeeder::class,
            ExpenseSeeder::class,
        ]);

        if (app()->environment(['local', 'development'])) {
            $this->call(DashboardDemoSeeder::class);
        }
    }
}
