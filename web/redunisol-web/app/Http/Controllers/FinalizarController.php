<?php

namespace App\Http\Controllers;

use App\Models\SiteSetting;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

class FinalizarController extends Controller
{
    public function show(Request $request): Response
    {
        $solicitud = [
            'monto'  => $request->query('monto', ''),
            'cuotas' => $request->query('cuotas', ''),
            'nro'    => $request->query('nro', ''),
        ];

        $getSettingOrEnv = function (string $settingKey, string $envKey, $default = '') {
            $setting = SiteSetting::get($settingKey, null);

            if (!is_null($setting) && $setting !== '') {
                return (string) $setting;
            }

            $env = env($envKey, null);

            if (!is_null($env) && $env !== '') {
                return (string) $env;
            }

            return (string) $default;
        };

        $settings = [
            'heading'          => $getSettingOrEnv('finalizar_heading', 'FINALIZAR_HEADING', 'Termina tu Solicitud'),
            'subheading'       => $getSettingOrEnv('finalizar_subheading', 'FINALIZAR_SUBHEADING', 'Su préstamo será descontado de la siguiente forma:'),
            'contact_question' => $getSettingOrEnv('finalizar_contact_question', 'FINALIZAR_CONTACT_QUESTION', '¿Tiene otra consulta para hacernos?'),
            'tna'              => $getSettingOrEnv('finalizar_tna', 'FINALIZAR_TNA', ''),
            'tea'              => $getSettingOrEnv('finalizar_tea', 'FINALIZAR_TEA', ''),
            'tnm'              => $getSettingOrEnv('finalizar_tnm', 'FINALIZAR_TNM', ''),
            'cft'              => $getSettingOrEnv('finalizar_cft', 'FINALIZAR_CFT', ''),
            'terms_url'        => $getSettingOrEnv('finalizar_terms_url', 'FINALIZAR_TERMS_URL', '/terminos-y-condiciones'),
            'contact_email'    => $getSettingOrEnv('finalizar_contact_email', 'FINALIZAR_CONTACT_EMAIL', SiteSetting::get('contact_email', 'contacto@redunisol.com.ar')),
            'whatsapp_url'     => $getSettingOrEnv('finalizar_whatsapp_url', 'FINALIZAR_WHATSAPP_URL', ''),
            'facebook_url'     => $getSettingOrEnv('finalizar_facebook_url', 'FINALIZAR_FACEBOOK_URL', ''),
            'external_api_url' => $getSettingOrEnv('finalizar_api_url', 'FINALIZAR_API_URL', ''),
            'external_api_user'=> $getSettingOrEnv('finalizar_api_user', 'FINALIZAR_API_USER', ''),
            'external_api_pass'=> $getSettingOrEnv('finalizar_api_pass', 'FINALIZAR_API_PASS', ''),
        ];

        return Inertia::render('finalizar', [
            'settings'  => $settings,
            'solicitud' => $solicitud,
        ]);
    }
}
