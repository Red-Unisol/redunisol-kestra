<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{{ config('app.name', 'Herramientas Red Unisol') }}</title>
        <link rel="preconnect" href="https://fonts.bunny.net">
        <link href="https://fonts.bunny.net/css?family=manrope:400,500,600,700,800" rel="stylesheet" />
        @vite(['resources/css/app.css'])
    </head>
    <body>
        <main class="disabled-shell">
            <section class="disabled-panel">
                <p class="disabled-panel__eyebrow">Herramientas Red Unisol</p>
                <h1 class="disabled-panel__title">Pagina de desarrollo</h1>
                <p class="disabled-panel__copy">
                    Por favor utilizar <strong>herramientas.redunisol.com.ar</strong>.
                </p>
            </section>
        </main>
    </body>
</html>
