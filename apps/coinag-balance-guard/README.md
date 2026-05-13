# Coinag Balance Guard

Unidad operativa independiente para mantener una cuenta Coinag por encima de un saldo minimo.

En cada ejecucion:

1. consulta `SaldoActual` de la cuenta monitoreada;
2. si el saldo es mayor o igual al minimo, no hace nada;
3. si el saldo esta por debajo, calcula el faltante;
4. consulta saldo de la cuenta fondeadora;
5. envia una transferencia por el faltante desde la fondeadora hacia la monitoreada.

La cuenta fondeadora puede operar en descubierto. Su saldo se guarda en auditoria, pero no bloquea el fondeo si es menor al faltante o negativo.

Por seguridad, `BALANCE_GUARD_DRY_RUN` viene en `true` por defecto. Para transferir de verdad hay que definirlo en `false`.

## Configuracion

Copiar `.env.example` a un archivo fuera de Git, por ejemplo:

```bash
sudo mkdir -p /opt/coinag-balance-guard
sudo cp .env.example /opt/coinag-balance-guard/coinag-balance-guard.env
sudo nano /opt/coinag-balance-guard/coinag-balance-guard.env
```

Variables principales:

- `COINAG_BALANCE_API_BASE`: base para `SaldoActual`.
- `COINAG_TRANSFER_API_BASE`: base v2 para `Transferencia`.
- `COINAG_TOKEN_URL`: endpoint OAuth/token.
- `COINAG_USERNAME` / `COINAG_PASSWORD`: credenciales API.
- `BALANCE_GUARD_MONITORED_*`: cuenta que debe quedar con fondos.
- `BALANCE_GUARD_SOURCE_*`: cuenta desde donde se fondea.
- `BALANCE_GUARD_MINIMUM_BALANCE`: default `30000000`.
- `BALANCE_GUARD_DRY_RUN`: `true` por defecto; poner `false` para transferir.

## Ejecucion manual

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m coinag_balance_guard --env-file /opt/coinag-balance-guard/coinag-balance-guard.env
```

## Systemd timer

El timer corre una vez despues del arranque y luego cada 5 minutos.

```bash
sudo cp systemd/coinag-balance-guard.service /etc/systemd/system/
sudo cp systemd/coinag-balance-guard.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now coinag-balance-guard.timer
systemctl list-timers coinag-balance-guard.timer
```

La app usa:

- lock: `/var/lib/coinag-balance-guard/balance_guard.lock`
- auditoria: `/var/lib/coinag-balance-guard/balance_guard_events.jsonl`
- trazas HTTP sanitizadas: `/var/lib/coinag-balance-guard/coinag_http_events.jsonl`

El cooldown evita reenviar fondeos si el saldo tarda en reflejar la transferencia. Default: 900 segundos.

## Cron

Si preferis cron en vez de systemd timer:

```bash
sudo crontab cron/coinag-balance-guard.cron
sudo crontab -l
```

Ese crontab ejecuta al reiniciar la VPS y cada 5 minutos.

## Operacion pendiente

El runbook para activar cuando la IP de la VPS este whitelisteada esta en:

- `docs/OPERATIONS.md`
