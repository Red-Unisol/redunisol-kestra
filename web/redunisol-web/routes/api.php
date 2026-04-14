<?php

use App\Http\Controllers\PdfSearchController;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\Facades\Storage;

Route::post('/pdf/search', PdfSearchController::class)->name('api.pdf.search');

Route::post('/recibos/upload', function (Request $request) {
    $request->validate([
        'recibo' => 'required|file|mimes:jpg,jpeg,png,gif,pdf|max:10240',
    ]);

    $path = $request->file('recibo')->store('recibos', 'public');

    return response()->json([
        'url' => Storage::disk('public')->url($path),
    ]);
})->name('api.recibos.upload');

Route::post('/form/submit', function (Request $request) {
    $webhookUrl    = config('services.kestra.form_webhook');
    $timeoutSecs   = (int) config('services.kestra.form_webhook_timeout', 10);
    $defaultSource = config('services.kestra.form_lead_source');

    if (! $webhookUrl) {
        return response()->json(['error' => 'Webhook not configured'], 500);
    }

    $payload = $request->only([
        'email',
        'whatsapp',
        'cuil',
        'province',
        'employment_status',
        'payment_bank',
        'recibo_url',
    ]);

    if ($defaultSource) {
        $payload['lead_source'] = $defaultSource;
    }

    $response = Http::timeout($timeoutSecs)->post($webhookUrl, $payload);

    if ($response->successful()) {
        return response()->json(['ok' => true]);
    }

    return response()->json(['ok' => false], 502);
})->name('api.form.submit');
