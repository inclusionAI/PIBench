<?php

use App\Models\Enquiry;
use App\Models\FollowUp;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

test('soft deleting an enquiry cascades to follow ups and restore reverses it', function (): void {
    $enquiry = Enquiry::factory()->create();
    $followUp = FollowUp::factory()->create([
        'enquiry_id' => $enquiry->id,
    ]);

    $enquiry->delete();

    expect(FollowUp::withTrashed()->find($followUp->id))
        ->not->toBeNull()
        ->and(FollowUp::withTrashed()->find($followUp->id)?->trashed())->toBeTrue();

    $enquiry->restore();

    expect(FollowUp::find($followUp->id))
        ->not->toBeNull()
        ->and(FollowUp::find($followUp->id)?->trashed())->toBeFalse();
});
