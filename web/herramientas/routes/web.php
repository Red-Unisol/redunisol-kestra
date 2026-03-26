<?php

use App\Http\Controllers\HerramientasController;
use Illuminate\Foundation\Http\Middleware\VerifyCsrfToken;
use Illuminate\Support\Facades\Route;

Route::get('/', [HerramientasController::class, 'index'])->name('home');

Route::post('/api/tools/consulta-renovacion-cruz-del-eje', [HerramientasController::class, 'consultaRenovacionCruzDelEje'])
    ->withoutMiddleware([VerifyCsrfToken::class])
    ->name('tools.consulta-renovacion-cruz-del-eje');
