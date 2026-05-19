# Contabilidad

Dominio para automatizaciones especificas de contabilidad.

## Transfer Vimarx

Flow principal:

- `contabilidad_transfer_vimarx_diario`
- namespace runtime por ambiente: `redunisol.<env>.contabilidad`
- schedule prod: todos los dias a las 04:00 `America/Argentina/Buenos_Aires`

Proceso:

1. descarga desde SFTP los archivos `mov_emp_431*.txt` de la raiz remota
2. excluye `mov_emp_mes_*`
3. ejecuta el cruce contra la API Vimarx
4. genera dos Excel por fecha de corrida:
   - `cruce_mov_emp_vimarx_YYYYMMDD.xlsx`
   - `cruce_mov_emp_vimarx_altos_YYYYMMDD.xlsx`
5. guarda `metadata.json` junto al output

Storage esperado en VPS:

```text
/opt/kestra/data/contabilidad-transfer/YYYY-MM-DD/
```

El task Docker monta esa ruta como:

```text
/data/contabilidad-transfer
```

Secrets requeridos en Kestra:

- `CONTABILIDAD_SFTP_HOST`
- `CONTABILIDAD_SFTP_USERNAME`
- `CONTABILIDAD_SFTP_PASSWORD`
- `DEVEXPRESS_EVALUATE_API_BASE_URL`

Frontend oculto:

```text
/contabilidad/77q330j56z
```

El slug puede cambiarse en `web/herramientas` con `CONTABILIDAD_TRANSFER_PRIVATE_SLUG`.
