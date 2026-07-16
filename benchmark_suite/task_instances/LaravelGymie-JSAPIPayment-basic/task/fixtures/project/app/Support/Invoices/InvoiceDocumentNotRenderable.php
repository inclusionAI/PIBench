<?php

namespace App\Support\Invoices;

use RuntimeException;

/**
 * Thrown when an invoice PDF cannot be rendered due to missing required data.
 */
final class InvoiceDocumentNotRenderable extends RuntimeException
{
    /**
     * @param  array{
     *   missing: list<string>,
     *   invoice: \App\Models\Invoice,
     *   member?: \App\Models\Member|null,
     *   subscription?: \App\Models\Subscription|null,
     *   plan?: \App\Models\Plan|null,
     *   settings?: array<string, mixed>,
     *   generated_at?: string,
     *   logo_data_uri?: string|null,
     * }  $viewData
     */
    public function __construct(public readonly array $viewData)
    {
        $missing = $viewData['missing'];
        $missingText = $missing ? implode(', ', $missing) : 'Missing required data';

        parent::__construct("Invoice document cannot be rendered: {$missingText}");
    }
}
