# Coinag Balance Guard - Operacion

## Estado actual

Fecha: 2026-05-12

Instalado en la nueva VPS:

- host: `vps-5967792-x.dattaweb.com`
- destino: `/opt/coinag-balance-guard`
- env real: `/opt/coinag-balance-guard/coinag-balance-guard.env`
- cron preparado: `/etc/cron.d/coinag-balance-guard`
- estado cron: preparado pero desactivado, con las lineas comentadas
- estado ejecucion: `BALANCE_GUARD_DRY_RUN=true`

Motivo de dejarlo desactivado:

- la IP de la VPS todavia no esta whitelisteada en Coinag
- no queremos generar errores repetidos ni ensuciar logs cada 5 minutos

## Secuencia pendiente

Cuando Coinag confirme que la IP de la VPS esta whitelisteada:

1. Activar el cron, manteniendo `BALANCE_GUARD_DRY_RUN=true`.
2. Dejarlo correr un rato en dry run.
3. Revisar logs operativos y HTTP sanitizados.
4. Si los logs se ven correctos, cambiar `BALANCE_GUARD_DRY_RUN=false`.
5. Dejar el cron activo en modo real.

## Activar cron en dry run

Verificar que el entorno sigue en dry run:

```bash
grep '^BALANCE_GUARD_DRY_RUN=' /opt/coinag-balance-guard/coinag-balance-guard.env
```

Debe devolver:

```text
BALANCE_GUARD_DRY_RUN=true
```

Activar el cron descomentando las dos lineas de schedule:

```bash
sudo sed -i 's/^# \\(@reboot root cd \\/opt\\/coinag-balance-guard.*\\)$/\\1/' /etc/cron.d/coinag-balance-guard
sudo sed -i 's/^# \\(\\*\\/5 \\* \\* \\* \\* root cd \\/opt\\/coinag-balance-guard.*\\)$/\\1/' /etc/cron.d/coinag-balance-guard
```

Verificar:

```bash
grep -E '^(@reboot|\\*/5)' /etc/cron.d/coinag-balance-guard
```

## Revisar logs dry run

Logs esperados:

```bash
tail -n 50 /var/log/coinag-balance-guard/cron.log
tail -n 20 /var/lib/coinag-balance-guard/balance_guard_events.jsonl
tail -n 20 /var/lib/coinag-balance-guard/coinag_http_events.jsonl
```

Eventos esperados:

- `balance_ok`: no requiere fondeo
- `dry_run_topup`: hubiera transferido, pero dry run impidio el POST real

En dry run no debe existir evento `topup_submitted`.

## Pasar a modo real

Solo hacer esto despues de revisar dry runs correctos:

```bash
sudo sed -i 's/^BALANCE_GUARD_DRY_RUN=.*/BALANCE_GUARD_DRY_RUN=false/' /opt/coinag-balance-guard/coinag-balance-guard.env
grep '^BALANCE_GUARD_DRY_RUN=' /opt/coinag-balance-guard/coinag-balance-guard.env
```

Debe devolver:

```text
BALANCE_GUARD_DRY_RUN=false
```

## Rollback rapido

Para volver a modo dry run:

```bash
sudo sed -i 's/^BALANCE_GUARD_DRY_RUN=.*/BALANCE_GUARD_DRY_RUN=true/' /opt/coinag-balance-guard/coinag-balance-guard.env
```

Para desactivar cron:

```bash
sudo sed -i 's/^\\(@reboot root cd \\/opt\\/coinag-balance-guard.*\\)$/# \\1/' /etc/cron.d/coinag-balance-guard
sudo sed -i 's/^\\(\\*\\/5 \\* \\* \\* \\* root cd \\/opt\\/coinag-balance-guard.*\\)$/# \\1/' /etc/cron.d/coinag-balance-guard
```
