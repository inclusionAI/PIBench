<?php

use App\Models\Invoice;
use App\Support\Invoices\InvoiceDocument;
use Illuminate\Foundation\Testing\RefreshDatabase;

uses(RefreshDatabase::class);

test('invoice document view renders Inter font faces and zero page margin css', function (): void {
    $invoice = Invoice::factory()->create([
        'total_amount' => 1000,
    ]);

    $html = view('invoices.document', InvoiceDocument::viewData($invoice))->render();

    expect($html)
        ->toContain("font-family: 'Inter'")
        ->toContain('font-weight: 800;')
        ->toContain('@page {')
        ->toContain('margin: 0mm;');
});
