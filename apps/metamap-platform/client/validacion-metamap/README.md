# Validacion MetaMap

Cliente desktop privado para monitorear validaciones MetaMap del dia.

No forma parte del hub web y no expone nada publicamente. Corre localmente en la PC operativa, consulta el `metamap-platform/server`, enriquece cada validacion con datos del core financiero y muestra tarjetas grandes con:

- nombre
- linea
- numero de solicitud
- CUIL
- monto

Tambien refresca cada 20 segundos y dispara una notificacion local de Windows cuando aparece una validacion nueva.

## Estructura

- `src/main.rs`: arranque de la app nativa
- `src/app.rs`: UI, polling y manejo de eventos
- `src/server_client.rs`: consulta a `GET /api/v1/validations`
- `src/core_client.rs`: consultas `EvaluateList` al core financiero
- `src/notifications.rs`: notificaciones locales de Windows
- `src/config.rs`: carga de configuracion desde entorno o archivo local

## Configuracion

1. Copiar `validacion-metamap.env.example` a `validacion-metamap.env`
2. Completar:
   - `VALIDACION_METAMAP_SERVER_BASE_URL`
   - `VALIDACION_METAMAP_SERVER_CLIENT_ID`
   - `VALIDACION_METAMAP_SERVER_CLIENT_SECRET`
   - `VALIDACION_METAMAP_CORE_BASE_URL`
3. Dejar el archivo al lado del ejecutable o definir `VALIDACION_METAMAP_CONFIG_PATH`

## Desarrollo local

```powershell
cargo run
```

## Build

```powershell
cargo build --release
```

El ejecutable espera `validacion-metamap.env` en el mismo directorio, salvo que se defina `VALIDACION_METAMAP_CONFIG_PATH`.
