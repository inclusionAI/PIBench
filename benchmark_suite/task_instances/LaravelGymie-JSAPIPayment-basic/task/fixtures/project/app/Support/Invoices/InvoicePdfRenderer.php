<?php

namespace App\Support\Invoices;

use App\Models\Invoice;
use Barryvdh\DomPDF\Facade\Pdf;
use Illuminate\Support\Facades\File;

/**
 * Render invoice PDFs for both UI download/preview and email attachments.
 *
 * This is the single source of truth for PDF output to ensure:
 * - consistent layout
 * - consistent missing-data guardrails
 * - consistent DomPDF font-cache directory handling
 */
final class InvoicePdfRenderer
{
    /**
     * Render an invoice to PDF bytes.
     *
     * @throws InvoiceDocumentNotRenderable
     */
    public function render(Invoice $invoice): string
    {
        $this->ensureDompdfFontCacheDirectoryExists();

        $data = InvoiceDocument::viewData($invoice);

        if ($data['missing'] !== []) {
            throw new InvoiceDocumentNotRenderable($data);
        }

        return Pdf::loadView('invoices.document', $data)
            ->setPaper('a4')
            ->output();
    }

    /**
     * Ensure DomPDF can write generated font metric files.
     */
    private function ensureDompdfFontCacheDirectoryExists(): void
    {
        File::ensureDirectoryExists(storage_path('fonts'));
    }
}
