<?php

namespace App\Http\Controllers\Api\V1;

use App\Http\Requests\Api\V1\InvoiceTransactionStoreRequest;
use App\Http\Resources\V1\InvoiceTransactionResource;
use App\Models\Invoice;
use App\Models\InvoiceTransaction;
use App\Services\Api\QueryFilters;
use App\Support\Data;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\Resources\Json\AnonymousResourceCollection;

/**
 * Nested invoice transaction endpoints.
 */
class InvoiceTransactionsController extends ApiController
{
    /**
     * List transactions for an invoice.
     */
    public function index(Request $request, Invoice $invoice): AnonymousResourceCollection
    {
        $this->requirePermission($request, 'View:Invoice');

        $perPage = QueryFilters::perPage($request->query('per_page'), default: 25);

        $transactions = $invoice->transactions()
            ->orderByDesc('occurred_at')
            ->paginate($perPage);

        return InvoiceTransactionResource::collection($transactions);
    }

    /**
     * Create a payment/refund transaction for an invoice.
     */
    public function store(InvoiceTransactionStoreRequest $request, Invoice $invoice): InvoiceTransactionResource
    {
        $this->requirePermission($request, 'Update:Invoice');

        $data = $request->validated();

        $transaction = $invoice->transactions()->create([
            'type' => $data['type'],
            'amount' => $data['amount'],
            'occurred_at' => $data['occurred_at'] ?? now()->timezone(\App\Support\AppConfig::timezone()),
            'payment_method' => $data['payment_method'] ?? $invoice->payment_method,
            'note' => $data['note'] ?? null,
            'reference_id' => $data['reference_id'] ?? null,
            'created_by' => Data::int($this->currentUser($request)->getAuthIdentifier(), 0),
        ]);

        return new InvoiceTransactionResource($transaction);
    }

    /**
     * Delete a transaction belonging to an invoice.
     */
    public function destroy(Request $request, Invoice $invoice, InvoiceTransaction $transaction): JsonResponse
    {
        $this->requirePermission($request, 'Update:Invoice');

        abort_unless((int) $transaction->invoice_id === (int) $invoice->id, 404);

        $transaction->delete();

        return $this->noContent();
    }
}
