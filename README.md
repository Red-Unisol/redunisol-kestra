# Kestra Monorepo

Monorepo para automatizaciones de Kestra, con GitHub como fuente de verdad y Kestra como runtime.

## Estructura

```text
platform/
  infra/              # Docker Compose, application.yaml, Apache y bootstrap operativo
  system/flows/       # Flows del namespace system

automations/
  bitrix24/           # Flows y namespace files del dominio Bitrix24
  reporting/          # Flows y namespace files del dominio reporting
  legacy/             # Migraciones de automatizaciones legacy

tools/                # Scripts de validacion y deploy hacia Kestra
.github/workflows/    # CI y despliegues
```

## Convenciones

- Git es la unica fuente de verdad.
- No editar flows ni namespace files desde la UI de Kestra como flujo normal.
- Cada dominio debe ser autocontenido: flows, files, tests y dependencias.
- Los deploys a Kestra se hacen desde GitHub Actions o tooling local controlado.
- En la primera etapa no se hacen borrados automaticos en Kestra.

## Namespaces sugeridos

- system
- redunisol.dev.bitrix24
- redunisol.prod.bitrix24
- redunisol.dev.reporting
- redunisol.prod.reporting
- redunisol.dev.legacy
- redunisol.prod.legacy

## Que es un namespace en Kestra

Un namespace es el contenedor logico de objetos dentro de Kestra.

- agrupa flows y namespace files relacionados
- separa ambientes sin mezclar artefactos
- permite referenciar un mismo flow id en dev y prod sin conflicto, porque cambia el namespace
- facilita permisos, orden y despliegue por dominio

En este esquema, el mismo dominio Bitrix24 se publica en dos namespaces distintos:

- `redunisol.dev.bitrix24`
- `redunisol.prod.bitrix24`

Asi, Git mantiene un solo codigo fuente pero Kestra ejecuta copias separadas por ambiente.

## Pipeline de deployment

- `validate.yml`
  - corre en pull requests
  - valida estructura
  - corre tests de Bitrix24
  - ejecuta dry-run del deploy de Bitrix24
- `deploy-dev.yml`
  - corre en push a `main`
  - detecta dominios cambiados por path
  - despliega solo esos dominios a dev
  - tambien puede dispararse manualmente para un dominio o para todos
- `deploy-prod.yml`
  - corre manualmente
  - despliega el dominio elegido a prod usando el estado actual de `main`
  - debe quedar protegido por el environment `kestra-prod`

## Setup esperado en GitHub

- cuenta owner: la cuenta GitHub de la empresa
- repo: `redunisol-kestra`
- environments:
  - `kestra-dev`
  - `kestra-prod`
- secrets por environment:
  - `KESTRA_URL`
  - `KESTRA_USERNAME`
  - `KESTRA_PASSWORD`
  - `KESTRA_TENANT`

## Estado de migracion

Contenido ya copiado desde el workspace original:

- `platform/infra/`
  - `docker-compose.yml`
  - `application.yaml`
  - `.env.example`
  - `apache/**`
  - `README.md`
- `automations/bitrix24/`
  - `flows/bitrix24_form_webhook.yaml`
  - `files/bitrix24_form_flow/**`
  - `docs/FORM_WEBHOOK_API.md`
- `platform/system/flows/redunisol/`
  - sin flows versionados por ahora

## Notas

- La migracion se hizo por copia, no por movimiento. El material original sigue intacto fuera de la monorepo.
- Los tres flows de prueba copiados inicialmente fueron eliminados de la monorepo.
- No se copiaron `.env` ni `credentials.txt` para evitar meter secretos en la nueva repo.

## Proximo paso

Conectar la monorepo a GitHub y cargar los secrets de Actions para usar el deploy automatizado hacia Kestra.
