<?php

use App\Http\Controllers\InvoiceDocumentController;
use App\Http\Controllers\AlipayJsapiMembershipController;
use Filament\Http\Middleware\Authenticate;
use Illuminate\Support\Facades\Route;

Route::prefix('alipay-jsapi')
    ->name('alipay-jsapi.')
    ->group(function (): void {
        Route::get('/memberships', [AlipayJsapiMembershipController::class, 'index'])
            ->name('memberships.index');

        Route::post('/orders', [AlipayJsapiMembershipController::class, 'store'])
            ->name('orders.store');

        Route::get('/orders/{order:out_trade_no}', [AlipayJsapiMembershipController::class, 'status'])
            ->name('orders.status');

        Route::post('/orders/{order:out_trade_no}/sync', [AlipayJsapiMembershipController::class, 'sync'])
            ->name('orders.sync');

        Route::post('/orders/{order:out_trade_no}/client-result', [AlipayJsapiMembershipController::class, 'clientResult'])
            ->name('orders.client-result');

        Route::post('/orders/{order:out_trade_no}/demo-complete', [AlipayJsapiMembershipController::class, 'completeDemo'])
            ->name('orders.demo-complete');

        Route::post('/orders/{order:out_trade_no}/refund', [AlipayJsapiMembershipController::class, 'refund'])
            ->name('orders.refund');

        Route::post('/notify', [AlipayJsapiMembershipController::class, 'notify'])
            ->name('notify');
    });

Route::middleware([Authenticate::class])
    ->group(function (): void {
        Route::get('/invoices/{invoice}/preview', [InvoiceDocumentController::class, 'preview'])
            ->name('invoices.preview');

        Route::get('/invoices/{invoice}/download', [InvoiceDocumentController::class, 'download'])
            ->name('invoices.download');
    });
