<?php

use App\Http\Controllers\InvoiceDocumentController;
use App\Http\Controllers\MembershipCheckoutController;
use Filament\Http\Middleware\Authenticate;
use Illuminate\Support\Facades\Route;

Route::prefix('membership-checkout')
    ->name('membership-checkout.')
    ->group(function (): void {
        Route::get('/memberships', [MembershipCheckoutController::class, 'index'])
            ->name('memberships.index');
    });

Route::middleware([Authenticate::class])
    ->group(function (): void {
        Route::get('/invoices/{invoice}/preview', [InvoiceDocumentController::class, 'preview'])
            ->name('invoices.preview');

        Route::get('/invoices/{invoice}/download', [InvoiceDocumentController::class, 'download'])
            ->name('invoices.download');
    });
