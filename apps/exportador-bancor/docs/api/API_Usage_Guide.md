DevExpress Evaluate API Guide
=============================

This guide consolidates the observed usage patterns of the Evaluate endpoints
and folds in the BOModel knowledge that is required to formulate useful
queries. For a deeper, per-entity field listing see
[BOModel_API_Reference.md](BOModel_API_Reference.md).

Environment & Access
--------------------
- **Host:** `https://celesol.dyndns.org:5050`
- **Endpoints:**  
  - `GET  /api/Empresa/Evaluate`  
  - `POST /api/Empresa/EvaluateObj`  
  - `POST /api/Empresa/EvaluateList`
- **TLS:** Internal certificate. Use `verify=False` (Python) or `-k` (curl).
- **Authentication:** None observed in captured flows.
- **GET + body required:** The `Evaluate` endpoint still expects a JSON body even
  when called with `GET`. Omitting it (or sending form data) yields `415
  Unsupported Media Type` or `400 A non-empty request body is required`.

ARC Export Field Checklist
--------------------------
- Use the ARC export pipeline field list as the canonical reference when requesting CuotaPrestamo data. It extends the historic selection with `Prestamo.[Cuota Resultante Prestamo]` while retaining the socio banking detail (`CuentaBancariaHabitual.*`, `SocAux.Caja40`).
- Keep the existing filter (`[NroCuota] > 0 AND [SaldoCuota] > 0.0m AND [Fecha] <= #2025-10-31# AND [Prestamo.LineaPrestamo.Superior.Descripcion] = 'LINEAS CBU BANCOS VARIOS'`) unless a run explicitly requires a different date.
- Future pagination changes should preserve the same column order so the consolidation logic can continue to hydrate the ARC layout without additional mapping.

Shared Payload (`QueryRequest`)
-------------------------------
All three endpoints accept the same JSON envelope:

```json
{
  "cmd": "<criteria or expression>",
  "tipo": "<fully qualified XPO type name>",
  "campos": "<projection>",
  "max": <int>,
  "opciones": "<optional flags>"
}
```

- `cmd`: DevExpress criteria language expression. Mandatory except for pure
  aggregation (`Evaluate`).
- `tipo`: Exact `Type Name` from the BOModel (case-sensitive, namespace included).
- `campos`:  
  - Omit for scalar `Evaluate` expressions.  
  - Single property (`"NombreCompleto"`) or semicolon-separated path
    (`"Prestamo.NroCuenta;Prestamo.SocioTitular.Socio.NroDoc"`).  
  - Commas cause `single criterion expected` errors.
- `max`: Upper bound for `EvaluateList` row count (ignored elsewhere).
- `opciones`: Unused in current scenarios; leave null/empty.

Criteria Primer
---------------
- **Objects:** `[<Namespace.Type>]` enumerates all instances (e.g.
  `[<F.Module.SocioMutual>]`).
- **Paths:** `[Prestamo.SocioTitular.Socio.NroDoc]` uses dot navigation. For
  collections, filter with nested criteria (e.g.
  `[DetalleCuotas][NroCuota = 1].Fecha`).
- **Comparisons:** Standard operators (`=`, `<`, `>`, `<>`, `Between`, `Like`).
- **Literals:**  
  - Strings: single quotes (`"[Referencia]='8113'"`).  
  - Dates: `#YYYY-MM-DD#`.  
  - Decimals: append `m` (`0.0m`).  
  - Null checks: `Is Null`, `Is Not Null`.
- **Aggregates:** Use `.Count()`, `.Sum(Field)` etc. on collections or object
  sets: `"[<F.Module.SocioMutual>].Count()"`.

Value Handling Notes
--------------------
- When you build payloads with a serializer (PowerShell `ConvertTo-Json`, `jq -n`,
  Python `json`), write string criteria as `[Field]='value'`; additional doubling
  of quotes (e.g. `''value''`) causes the parser to throw `syntax error`.
- Enumerations (`Prestamo.Estado`, `Prestamo.EstadoPrestamo`, `Solicitud.EstadoBase`,
  etc.) come back as numeric codes. Map them to friendly names on the client.
- Monetary fields can be negative even when they normally represent amounts due
  (e.g. `CuotaPrestamo.PunitoriosPendientes` becomes negative when credits were
  applied).
- Missing navigation targets result in literal `null` entries in the response
  (e.g. `Prestamo.Garantia.*` for unsecured loans).
- Rate information for loan lines lives in properties such as
  `LineaPrestamo.TasaMinima`/`TasaMaxima`; querying plain `LineaPrestamo.Tasa`
  throws the `"El camino de la propiedad 'Tasa' no es correcto..."` error.

Command-Line Workflow (WSL/Fedora)
----------------------------------
- **Base command:** `curl -k -H 'Content-Type: application/json' -X <VERB> "$EVAL_BASE/api/Empresa/<Endpoint>" --data-binary @payload.json`
  where `$EVAL_BASE` defaults to `https://celesol.dyndns.org:5050`.
- **Set environment variables once per shell:** `export EVAL_BASE=https://celesol.dyndns.org:5050`.
- **Create payloads without quoting headaches:** Use here-docs (`cat <<'EOF' > payloads/example.json ... EOF`) or
  `jq -n --arg cmd "[<F.Module.SocioMutual>].Count()" '{cmd:$cmd}' > payloads/count_socios.json`.
- **Evaluate GET behaviour:** Always include `--data-binary @payload.json` with `-X GET`; omitting the body reproduces `415` or `400` errors.
- **Inspect responses:** Pipe through `jq` (`curl ... | jq`) to pretty-print JSON, or redirect to disk for audit (`curl ... > responses/run-$(date +%s).json`).

Endpoint Behaviour
------------------
### `GET /api/Empresa/Evaluate`
- Expects a scalar expression (`cmd` required, `tipo`/`campos` ignored).
- Typical use: counts, sums, boolean exist checks.
- Returns plain values (number, string, boolean). HTTP 405 if POSTed.

### `POST /api/Empresa/EvaluateObj`
- Returns a **single** object projection for the requested type.
- `campos` drives output order. Missing matches yield HTTP 500 with
  `"No existe objeto con esas condiciones"`.
- Use when you expect exactly one row (e.g., one socio by document).

### `POST /api/Empresa/EvaluateList`
- Returns an array of rows (each row is an array aligned with `campos`).
- Honours `max` by truncating without raising.
- Large object projections (navigation properties with many children) may
  exhaust server memory; request scalar fields instead.

BOModel Touchpoints
-------------------
The types below are the ones most often queried. Refer to the BOModel summary
for full field lists.

| Type (`tipo`) | Purpose | Primary identifiers | High-value fields |
| --- | --- | --- | --- |
| `F.Module.SocioMutual` | Socio master record | `ID`, `Clave`, `NroSocio`, `NroDoc`, `ClaveBusqueda` | `NombreCompleto`, `Celular`, `CuentaBancariaHabitual`, `Prestamos`, `Solicitudes`, `ClasificacionPEP`, `Saldo` |
| `F.Module.Cuentas.CuentaPorSocio` | Link between socios and financial accounts | `ID`, `Socio.ID`, `Prestamo.ID` | `TipoRelacion`, `FechaAlta`, `Garantia`, `NroDocumento` |
| `F.Module.Cuentas.Prestamos.Prestamo` | Loan header | `ID`, `NroCuenta`, `Referencia` | `SocioTitular.Socio`, `LineaPrestamo`, `Destino`, `FechaEmision`, `Cuotas`, `MontoPrestamo`, `SaldoPrestamo`, `Estado (1)` |
| `F.Module.Cuentas.Prestamos.CuotaPrestamo` | Individual instalments | `ID`, `Prestamo.ID`, `NroCuota` | `Fecha`, `FechaCobro`, `Capital`, `Interes`, `MontoTotal`, `SaldoCuota`, `PunitoriosPendientes (2)`, `ProcesoDebitoPendiente` |
| `F.Module.Cuentas.Bancos.CuentaBancariaSocio` | Bank accounts for socios | `ID`, `Socio.ID` | `Nombre`, `CBU`, `NroCuenta`, `Moneda`, `TipoCuenta`, `Habitual` |
| `F.Module.Cuentas.Prestamos.GarantiaCuenta` | Pledged collateral | `ID`, `Prestamo.ID`, `CoDeudor.ID` | `TipoGarantia`, `Descripcion`, `ValorAproximado`, `Vencimiento`, `Solicitud` |
| `PreSolicitud.Module.Solicitud` | Credit applications | `Oid` (`ID`), `NroSolicitud` | `Fecha`, `Estado`, `LineaPrestamo`, `MontoAFinanciar`, `Cuotas`, `CuotaResultante`, `NroDocumento`, `NroSocio`, `Garante` |

`(1)` Enumerations are returned as integers; see Value Handling Notes.
`(2)` Penalty totals can be negative when credits were applied.

Navigation Highlights
---------------------
Use these paths to avoid guesswork when joining data across types:

- Loan holder document: `Prestamo.SocioTitular.Socio.NroDoc`
- Loan line metadata: `Prestamo.LineaPrestamo.Codigo;Prestamo.LineaPrestamo.Descripcion`
- Cuota balance snapshot: `CuotaPrestamo.SaldoCuota;CuotaPrestamo.PunitoriosPendientes`
- Default CBU for disbursement: `SocioMutual.CuentaBancariaHabitual.CBU`
- Account defaults: `SocioMutual.CuentaBancariaHabitual.Habitual` (true marks the primary bank account)
- Pre-solicitud outcome plus linked socio: `Solicitud.EstadoBase;Solicitud.NroSocio`
- Guarantee parties: `Prestamo.Garantias[].CoDeudor.NombreCompleto`

Practical Recipes (WSL-ready)
-----------------------------
Start once per session:

```bash
mkdir -p payloads responses
export EVAL_BASE=${EVAL_BASE:-https://celesol.dyndns.org:5050}
```

1. **Count socios**

   ```bash
   cat <<'EOF' > payloads/count_socios.json
   {"cmd":"[<F.Module.SocioMutual>].Count()"}
   EOF

   curl -k -X GET "$EVAL_BASE/api/Empresa/Evaluate" \
     -H 'Content-Type: application/json' \
     --data-binary @payloads/count_socios.json | tee responses/count_socios.json
   ```

   Expect a single number (e.g. `20003`).

2. **Lookup socio by document**

   ```bash
   DOC=44524078
   jq -n --arg doc "$DOC" '{
     cmd: "[NroDoc]="+$doc,
     tipo: "F.Module.SocioMutual",
     campos: "NombreCompleto;NroSocio"
   }' > payloads/socio_by_doc.json

   curl -k -X POST "$EVAL_BASE/api/Empresa/EvaluateObj" \
     -H 'Content-Type: application/json' \
     --data-binary @payloads/socio_by_doc.json | jq .
   ```

   Returns a single row array such as `["FIGUEROA PLOMER BIANCA NATALI",20278]`.

3. **Prestamo by reference**

   ```bash
   cat <<'EOF' > payloads/prestamo_ref_8113.json
   {
     "cmd": "[Referencia]='8113'",
     "tipo": "F.Module.Cuentas.Prestamos.Prestamo",
     "campos": "NroCuenta;Referencia;SocioTitular.Socio.NombreCompleto"
   }
   EOF

   curl -k -X POST "$EVAL_BASE/api/Empresa/EvaluateObj" \
     -H 'Content-Type: application/json' \
     --data-binary @payloads/prestamo_ref_8113.json | jq .
   ```

4. **Cuotas abiertas snapshot**

   ```bash
   cat <<'EOF' > payloads/cuotas_abiertas.json
   {
"cmd": "[NroCuota] > 0 AND [SaldoCuota] > 0.0m AND [Fecha] <= #2025-10-31# AND [Prestamo.LineaPrestamo.Descripcion] = 'LINEAS CBU BANCOS VARIOS'",
     "tipo": "F.Module.Cuentas.Prestamos.CuotaPrestamo",
     "campos": "NroCuota;Fecha;Capital;Interes;SaldoCuota;Prestamo.NroCuenta;Prestamo.SocioTitular.Socio.NombreCompleto",
     "max": 20000
   }
   EOF

   curl -k -X POST "$EVAL_BASE/api/Empresa/EvaluateList" \
     -H 'Content-Type: application/json' \
     --data-binary @payloads/cuotas_abiertas.json | jq .
   ```

5. **Pre-solicitudes for a specific day**

   ```bash
   RUN_DATE=2025-10-14
   jq -n --arg date "$RUN_DATE" '{
     cmd: ("[Fecha] = #"+$date+"#"),
     tipo: "PreSolicitud.Module.Solicitud",
     campos: "Oid;Fecha;Estado",
     max: 30
   }' > payloads/presolicitudes_by_day.json

   curl -k -X POST "$EVAL_BASE/api/Empresa/EvaluateList" \
     -H 'Content-Type: application/json' \
     --data-binary @payloads/presolicitudes_by_day.json | jq .
   ```

6. **Inspect metadata types**

   ```bash
   cat <<'EOF' > payloads/metadata_count.json
   {"cmd":"[<DevExpress.Xpo.XPObjectType>].Count()"}
   EOF

   curl -k -X GET "$EVAL_BASE/api/Empresa/Evaluate" \
     -H 'Content-Type: application/json' \
     --data-binary @payloads/metadata_count.json
   ```

Error Patterns
--------------
- `400` + `"El camino de la propiedad '<Field>' no es correcto..."`  
  -> Field path typo or wrong parent object; re-check the BOModel.
- `400` + `"Value cannot be null. (Parameter 'classType')"`  
  -> `tipo` string invalid (case or namespace).
- `400` + parser syntax error  
  -> Malformed criteria; ensure quotes/brackets paired.
- `500` + `"No existe objeto..."`  
  -> `EvaluateObj` found zero matches.
- `500` + `OutOfMemoryException`  
  -> `campos` pulled heavy graphs; restrict to scalar fields or set `max`.
- `405 Method Not Allowed`  
  -> Wrong HTTP verb for the endpoint.

Escaping & Tooling Tips
-----------------------
- Keep payloads in versioned files (`payloads/` folder) so curl calls can reuse
  `--data-binary @file`.
- Reach for structured generators when values are dynamic:  
  `jq -n --arg doc "$DOC" '{cmd:"[NroDoc]="+$doc,"tipo":"F.Module.SocioMutual","campos":"NombreCompleto;NroSocio"}'`  
  ```bash
  python3 - <<'PY' > payloads/doc_lookup.json
  import json, os
  print(json.dumps({
      "cmd": f"[NroDoc]={os.environ['DOC']}",
      "tipo": "F.Module.SocioMutual",
      "campos": "NombreCompleto;NroSocio"
  }))
  PY
  ```
- Pipe responses through `jq` (or `python -m json.tool`) to spot errors quickly.
- Save known-good requests as shell functions or scripts; copy/paste ad-hoc
  edits are the top source of criteria typos.

Next Steps
----------
- Use the cheat sheets above together with
  [BOModel_API_Reference.md](BOModel_API_Reference.md) to design projections
  that balance context with payload size.
- Document new field discoveries (type, property path, sample response) so the
  reference stays current.
