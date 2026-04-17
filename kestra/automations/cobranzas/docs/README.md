# Cobranzas

Dominio para automatizaciones de cobranzas y mora.

## Flows

- `bitrix_crm_negociaciones`: webhook principal que planifica acciones futuras en KV.
- `bitrix_crm_negociaciones_scheduler`: scheduler que recorre pendientes en KV y ejecuta las acciones vencidas.

## Logica actual

La automatizacion versionada en `bitrix_crm_negociaciones/**` ya no resuelve solo la etapa de promesa.
Ahora concentra la secuencia completa de negociaciones definida en `files/bitrix_crm_negociaciones/config.json`.

Arquitectura actual:

- el webhook planifica acciones futuras y las guarda en KV
- cada accion pendiente queda persistida con `status=pending`
- el scheduler corre cada 5 minutos
- antes de actuar revalida etapa, dependencia y nueva comunicacion
- cuando una accion termina queda marcada como `completed`, `cancelled` o `error`

Stages cubiertos hoy:

- `C11:NEW`
- `C11:UC_VO2IJO`
- `C11:PREPARATION`
- `C11:EXECUTING`
- `C11:UC_6KG2Z3`

Comportamiento general:

- reacciona a cambios de etapa en Bitrix24
- ignora updates que no cambian realmente de stage
- calcula acciones futuras respetando horario habil
- persiste pendientes en el KV Store de Kestra
- envia templates Edna segun la etapa cuando el scheduler los encuentra vencidos
- revalida el deal antes de cada envio o cambio de etapa
- corta la secuencia si el deal ya no sigue en la etapa esperada o si hubo nueva comunicacion despues del envio previo

## Configuracion

Configuracion runtime reutilizada:

- `envs.bitrix24_base_url`
- `envs.bitrix24_timeout_seconds`
- `secret('BITRIX24_WEBHOOK_PATH')`
- `secret('BITRIX24_CRM_NEGOCIACIONES_WEBHOOK_KEY')`
- `secret('BITRIX24_CRM_NEGOCIACIONES_APP_TOKEN')`
- `envs.bitrix24_promesa_date_field`
- `envs.bitrix24_promesa_amount_field`
- `envs.business_start_hour`
- `envs.business_start_minute`
- `envs.business_end_hour`
- `envs.business_end_minute`
- `envs.local_tz`
- `envs.edna_url`
- `envs.edna_sender`
- `envs.edna_timeout_seconds`
- `secret('EDNA_API_KEY')`

Configuracion versionada del embudo:

- `kestra/automations/cobranzas/files/bitrix_crm_negociaciones/config.json`

## Pruebas

Pruebas unitarias del dominio:

- `python -m unittest kestra.automations.cobranzas.tests.test_bitrix_crm_negociaciones`
