<?php

namespace Database\Seeders;

use App\Models\Plan;
use App\Models\Service;
use Illuminate\Database\Seeder;

class AlipayMembershipDemoSeeder extends Seeder
{
    /**
     * Seed deterministic membership plans for the public JSAPI checkout.
     */
    public function run(): void
    {
        $service = Service::updateOrCreate(
            ['name' => 'Membership Cards'],
            ['description' => 'Gym membership cards sold through the Alipay JSAPI checkout.']
        );

        $plans = [
            [
                'code' => 'ALIPAY-MONTHLY',
                'name' => 'Monthly Gym Pass',
                'description' => 'Unlimited gym floor access for 30 days.',
                'days' => 30,
                'amount' => 199,
            ],
            [
                'code' => 'ALIPAY-COACHING',
                'name' => '60-Day Coaching Pack',
                'description' => 'Membership card with private coaching sessions.',
                'days' => 60,
                'amount' => 699,
            ],
            [
                'code' => 'ALIPAY-ANNUAL',
                'name' => 'Annual Performance Card',
                'description' => 'A full year of access, classes, and member benefits.',
                'days' => 365,
                'amount' => 1599,
            ],
        ];

        foreach ($plans as $plan) {
            Plan::updateOrCreate(
                ['code' => $plan['code']],
                [
                    ...$plan,
                    'service_id' => $service->id,
                    'status' => 'active',
                ]
            );
        }
    }
}
