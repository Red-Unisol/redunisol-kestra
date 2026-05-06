<?php

namespace Tests\Feature;

use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class ConsultaCuadTest extends TestCase
{
    public function test_it_requires_a_cuil(): void
    {
        $response = $this->postJson('/api/tools/consulta-cuad', [
            'cuil' => '',
        ]);

        $response
            ->assertStatus(422)
            ->assertJsonValidationErrors(['cuil']);
    }

    public function test_it_proxies_the_request_to_kestra(): void
    {
        config()->set('tools.proxy.consulta_cuad_url', 'https://kestra.example.test/webhook');
        config()->set('tools.proxy.timeout_seconds', 90);

        Http::fake([
            'https://kestra.example.test/webhook' => Http::response([
                'ok' => true,
                'found' => true,
                'status' => 'ok',
                'cuil' => '20262769993',
                'bruto' => '1831808.25',
                'neto' => '763682.61',
                'cupo' => '515732.87',
                'afectado' => '860110.96',
                'disponible' => '0.00',
                'deuda' => '10149636.39',
                'captcha_attempts' => 5,
                'response_json' => '{"ok":true}',
                'error' => '',
            ], 200),
        ]);

        $response = $this->postJson('/api/tools/consulta-cuad', [
            'cuil' => '20-26276999-3',
        ]);

        $response
            ->assertOk()
            ->assertJsonPath('ok', true)
            ->assertJsonPath('found', true)
            ->assertJsonPath('cuil', '20262769993');

        Http::assertSent(function ($request): bool {
            return $request->url() === 'https://kestra.example.test/webhook'
                && $request['cuil'] === '20-26276999-3';
        });
    }
}
