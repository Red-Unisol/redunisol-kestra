<?php

namespace Tests\Feature;

use Tests\TestCase;

class DisabledSiteTest extends TestCase
{
    protected function setUp(): void
    {
        parent::setUp();

        $this->withoutVite();
    }

    public function test_home_shows_disabled_page_when_site_is_disabled(): void
    {
        config()->set('tools.enabled', false);

        $response = $this->get('/');

        $response
            ->assertStatus(503)
            ->assertSee('Pagina de desarrollo')
            ->assertSee('herramientas.redunisol.com.ar');
    }

    public function test_api_returns_service_unavailable_when_site_is_disabled(): void
    {
        config()->set('tools.enabled', false);

        $response = $this->postJson('/api/tools/consulta-cuad', [
            'cuil' => '20304050607',
        ]);

        $response
            ->assertStatus(503)
            ->assertJson([
                'ok' => false,
                'error' => 'development_site_disabled',
            ]);
    }
}
