<?php

namespace App\Http\Controllers;

use App\Models\Invoice;
use App\Support\Invoices\InvoiceDocument;
use App\Support\Invoices\InvoiceDocumentNotRenderable;
use App\Support\Invoices\InvoicePdfRenderer;
use Illuminate\Http\Response;
use Symfony\Component\HttpFoundation\BinaryFileResponse;

class InvoiceDocumentController extends Controller
{
    /**
     * Render an invoice preview as an inline PDF.
     */
    public function preview(Invoice $invoice, InvoicePdfRenderer $renderer): Response
    {
        $invoice = InvoiceDocument::loadForRendering($invoice);

        $this->authorize('view', $invoice);

        try {
            $pdfBytes = $renderer->render($invoice);
        } catch (InvoiceDocumentNotRenderable $exception) {
            return response()
                ->view('invoices.error', $exception->viewData)
                ->setStatusCode(200);
        }

        return response($pdfBytes, 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'inline; filename="'.InvoiceDocument::pdfFilename($invoice).'"',
        ]);
    }

    /**
     * Download the invoice as a PDF document.
     */
    public function download(Invoice $invoice, InvoicePdfRenderer $renderer): Response|BinaryFileResponse
    {
        $invoice = InvoiceDocument::loadForRendering($invoice);

        $this->authorize('view', $invoice);

        try {
            $pdfBytes = $renderer->render($invoice);
        } catch (InvoiceDocumentNotRenderable $exception) {
            return response()
                ->view('invoices.error', $exception->viewData)
                ->setStatusCode(422);
        }

        return response($pdfBytes, 200, [
            'Content-Type' => 'application/pdf',
            'Content-Disposition' => 'attachment; filename="'.InvoiceDocument::pdfFilename($invoice).'"',
        ]);
    }
}
