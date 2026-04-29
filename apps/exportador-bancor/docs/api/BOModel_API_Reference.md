BOModel API Reference (Distilled)
=================================

This note extracts the BOModel information that is most useful when crafting
requests against the DevExpress Evaluate endpoints. The focus is on the entity
types that appeared in traffic captures and that are the natural entry points
for lending, socios, and presolicitud workflows.

How to read it
--------------
- **Type Name** is the exact string required in the `tipo` field of the API
  payload (case-sensitive).
- **Field paths** can be chained in `campos`/`cmd` (e.g.
  `Prestamo.SocioTitular.Socio.NroDoc`).
- Only the most relevant fields are listed here. Many types expose dozens of
  calculated balances and audit helpers; those were omitted unless they are
  typically queried.

Key Entities
------------

### F.Module.SocioMutual (`Datos Personales`)

| Field | Type | Notes |
| --- | --- | --- |
| `ID`, `Clave` | int | Internal identifiers; hidden in UI but valid in queries. |
| `ClaveBusqueda` | string | `"Apellido, Nombre (NroDoc)"`. Handy for lookups. |
| `NroSocio` | int? | Membership number (nullable for prospects). |
| `NroDoc` | long | Documento principal; also exposed as `CuentaPorSocio.NroDocumento`. |
| `CUIT` | long | Tax identifier. |
| `Nombre`, `Apellido`, `NombreCompleto` | string | Person display data. |
| `FechaDeNacimiento`, `Edad`, `Sexo`, `EstadoCivil` | — | Demographics. |
| `Telefono`, `Celular`, `WhatsApp`, `Email` | string | Contact channels. |
| `DomicilioLaboral`, `CuentaBancariaHabitual`, `CuentaDebitoCtaSocial` | object | Main navigation nodes for address and payments. |
| `CategoriaActual`, `CategoriaFT`, `DadoDeBaja` | — | Membership category tracking. |
| `ClasificacionPEP`, `PEP`, `PEPExterno`, `SujetoObligado`, `VinculoPEP` | — | Compliance flags. |
| `Prestamos` | `IList<F.Module.Cuentas.Prestamos.Prestamo>` | All loans where the socio participates. |
| `Cuentas` | `XPCollection<F.Module.Cuentas.CuentaPorSocio>` | Join table to financial accounts. |
| `Solicitudes` | `XPCollection<PreSolicitud.Module.SolicitudBase>` | Historical and active credit applications. |
| `CuentaBancariaHabitual` | `F.Module.Cuentas.Bancos.CuentaBancariaSocio` | Use for `CBU`, `NroCuenta`, `SucursalBanco`. |
| `Saldo` | decimal | Sum of active balances across linked accounts. |

### F.Module.Cuentas.CuentaPorSocio

| Field | Type | Notes |
| --- | --- | --- |
| `ID` | int | Stable identifier. |
| `Socio` | `F.Module.SocioMutual` | Back-reference to the titular socio. |
| `Prestamo` | `F.Module.Cuentas.Prestamos.Prestamo` | When the record represents a loan holder. |
| `Cuenta` | `F.Module.Cuentas.Cuenta` | Underlying account entity (savings/credit/etc.). |
| `FechaAlta`, `FechaTerminacion` | DateTime | Lifecycle of the relation. |
| `NroDocumento` | long | Convenience mirror of the socio document number. |
| `Garantia` | `F.Module.Cuentas.Prestamos.GarantiaCuenta` | Per-loan guarantee snapshot, when applicable. |
| `TipoRelacion` | `F.Module.RelacionCuenta` | Role of the socio (Titular, Cotitular, Garante, etc.). |

### F.Module.Cuentas.Prestamos.Prestamo

| Field | Type | Notes |
| --- | --- | --- |
| `ID` | int | Internal key; hidden in UI but queryable. |
| `NroCuenta`, `Referencia` | long / string | Operational identifiers seen in legacy systems. |
| `Descripcion` | string | Free-form label; defaults to loan narrative. |
| `SocioTitular` | `F.Module.Cuentas.CuentaPorSocio` | Primary holder. Chain to `SocioTitular.Socio`. |
| `Integrantes` | `XPCollection<F.Module.Cuentas.CuentaPorSocio>` | All related socios (codeudores, garantes). |
| `LineaPrestamo` | `F.Module.Cuentas.Prestamos.LineaPrestamo` | Product line; exposes `Codigo`, `Descripcion`. |
| `Destino` | `F.Module.Cuentas.Prestamos.DestinoPrestamo` | Declared loan destination. |
| `Solicitud` | `PreSolicitud.Module.Solicitud` | Back-link to pre-solicitud when originated via channel. |
| `DetalleCuotas` | `XPCollection<F.Module.Cuentas.Prestamos.CuotaPrestamo>` | All scheduled instalments. |
| `Garantia`, `Garantias` | `GarantiaCuenta` | Current and historical pledges. |
| `FechaEmision`, `FechaPrimerVto`, `PrimerVencimiento` | DateTime | Key milestone dates. |
| `Cuotas`, `Plazo` | int | Total instalments / months. |
| `Capital`, `MontoPrestamo`, `MontoADesembolsar` | decimal | Principal amounts. |
| `Interes`, `TEA`, `TEM`, `TNA`, `Tabla de Tasas` | decimal | Interest configuration. |
| `Saldo`, `SaldoPrestamo`, `SaldoCapitalFT`, `SaldoInteresFT` | decimal | Current balances; prefer `SaldoPrestamo` to avoid FT-only columns. |
| `Estado`, `EstadoPrestamo`, `EstadoINAES`, `Clasificacion` | enum | Account state, credit risk staging (API returns numeric codes). |
| `CuentaDebitoCuotas`, `CuentaBancariaCobro` | account references | Payment instruments. |
| `ProcesosDebitos` | Debit processes | Relates to debit batches (AMV, CBU, etc.). |
| `LineaPrestamo.TasaMinima`, `LineaPrestamo.TasaMaxima` | decimal | Published min/max rates (no plain `LineaPrestamo.Tasa` property). |

### F.Module.Cuentas.Prestamos.CuotaPrestamo

| Field | Type | Notes |
| --- | --- | --- |
| `ID` | int | Internal key. |
| `Prestamo` | `F.Module.Cuentas.Prestamos.Prestamo` | Parent loan; use for chained queries. |
| `NroCuota` | int | Instalment number (0 for disbursement). |
| `Fecha`, `FechaCobro` | DateTime | Scheduled and last payment timestamps. |
| `Descripcion` | string | `${Prestamo.NroCuenta}/${NroCuota}`. |
| `Capital`, `Interes`, `Otros`, `MontoTotal` | decimal | Scheduled amounts. |
| `CapitalPago`, `InteresPago`, `TotalPago` | decimal | Amounts actually paid. |
| `SaldoCuota`, `SaldoCuotaCapital`, `SaldoCuotaInteres`, `SaldoCuotaConPunitorios` | decimal | Remaining balances. |
| `PunitoriosPagos`, `PunitoriosPendientes` | decimal | Late-payment charges; can be negative when credits are applied. |
| `ProcesoDebitoPendiente` | bool | Indicates pending automatic debit. |
| `ProcesosDebitos` | `XPCollection<C...ProcesoDebito>` | All related debit attempts. |

### F.Module.Cuentas.Prestamos.GarantiaCuenta

| Field | Type | Notes |
| --- | --- | --- |
| `ID` | int | Internal key. |
| `Prestamo` | `F.Module.Cuentas.Prestamos.Prestamo` | Loan secured by the guarantee. |
| `CoDeudor`, `Garante`, `Persona` | `F.Module.SocioMutual` / `ClasesBase.Persona` | Parties tied to the guarantee. |
| `Tipo` | `ClasesBase.TipoOtros` | Describes the guarantee asset. |
| `TipoGarantia` | `F.Module.Cuentas.Prestamos.ETipoGarantia?` | Enumerated guarantee category. |
| `Descripcion` | string | Textual description of the collateral. |
| `ValorAproximado`, `Fecha`, `Vencimiento` | decimal / DateTime | Valuation and lifecycle. |
| `UsoGlobal`, `Anulada` | bool | Availability / status flags. |
| `Solicitud` | `PreSolicitud.Module.Solicitud` | Link back to originating application (when applicable). |

### F.Module.Cuentas.Bancos.CuentaBancariaSocio

| Field | Type | Notes |
| --- | --- | --- |
| `ID` | int | Internal key. |
| `Socio` | `F.Module.SocioMutual` | Owner. |
| `Nombre` | string | Friendly label for the account. |
| `CBU`, `NroCuenta` | string | Banking identifiers. |
| `SucursalBanco` | int | Branch number. |
| `TipoCuenta` | `Contab.Cuentas.Bancos.TipoCuentaBancaria` | Account classification (CC, CA, etc.). |
| `Moneda` | `ClasesBase.Contab.Moneda` | Currency. |
| `Habitual` | bool | Flags the default account (used by `Socio.CuentaBancariaHabitual`). |
| `CuentaMutual`, `NoPropia` | bool | Whether account belongs to the mutual or to the socio. |
| `MontoMaximo`, `MontoEnviadoMes` | decimal | Operational caps for debit batches. |
| `InformeDebitos` | `XPCollection<C...ProcesoDebito>` | Debits tied to this instrument. |

### PreSolicitud.Module.Solicitud

| Field | Type | Notes |
| --- | --- | --- |
| `Oid` | int | Primary key (also exposed as `ID`). Use in filters. |
| `Fecha`, `FechaPrimerVencimiento`, `FechaUltimaCuota` | DateTime | Application and projected schedule. |
| `Estado` | `PreSolicitud.Module.EstadoSolicitud` | Detailed state (workflow). |
| `EstadoBase` | `PreSolicitud.Module.EEstadoSolicitud` | Simplified enum for filtering. |
| `MontoADesembolsar`, `MontoAFinanciar`, `MontoOriginal`, `Capital` | decimal | Principal figures. |
| `Cuotas`, `CuotaResultante` | int / decimal | Instalment count and amount. |
| `LineaPrestamo` | `F.Module.Cuentas.Prestamos.LineaPrestamo` | Target product. |
| `Destino` | `F.Module.Cuentas.Prestamos.DestinoPrestamo` | Use of funds. |
| `CuentaAMV`, `CuentaBancaria` | account refs | Chosen disbursement instruments. |
| `NroDocumento`, `NroSocio`, `CUIT` | long/int | Applicant identifiers (mirrors socio when already member). |
| `Actividad`, `ActividadPrincipal`, `Empleador` | — | Employment context. |
| `IngresosMensuales`, `IngresosMensualesConyuge`, `FacturacionMensual` | decimal/int | Income metrics. |
| `Garante`, `Garantes`, `Garantia` | Guarantee structures tied to the request. |
| `EjecutivoSolicitud`, `VendedorSolicitud` | workflow actors. |
| `Novedades`, `EstadoDocumentacion`, `Adjuntos` | Collections for tracking back-office progress. |

Navigation Cheat Sheet
----------------------
- Socio document from a prestamo: `Prestamo.SocioTitular.Socio.NroDoc`.
- Socio name from a cuota: `CuotaPrestamo.Prestamo.SocioTitular.Socio.NombreCompleto`.
- Loan reference and account pair: `Prestamo.Referencia;Prestamo.NroCuenta`.
- Loan line code and description: `Prestamo.LineaPrestamo.Codigo;Prestamo.LineaPrestamo.Descripcion`.
- Default bank account for a socio: `SocioMutual.CuentaBancariaHabitual.NroCuenta;SocioMutual.CuentaBancariaHabitual.CBU`.
- Application status plus linked loan account: `Solicitud.EstadoBase;Solicitud.LineaPrestamo.Descripcion;Solicitud.NroSocio`.
- Guarantee parties: `Prestamo.Garantias[].CoDeudor.NombreCompleto;Prestamo.Garantias[].ValorAproximado`.
- Instalment ageing vs. amounts: `CuotaPrestamo.AtrasoFT;CuotaPrestamo.SaldoCuota;CuotaPrestamo.PunitoriosPendientes`.
- Debit readiness: `CuotaPrestamo.ProcesoDebitoPendiente;CuotaPrestamo.ProcesosDebitos[].Estado`.
- Compliance snapshot for a socio: `SocioMutual.ClasificacionPEP;SocioMutual.SujetoObligado;SocioMutual.PEP`.

Query Tips Aligned with the Model
---------------------------------
- Use plural collections (e.g. `Prestamo.DetalleCuotas[]`) only in criteria, not in `campos`; for projections target scalar fields or chain further (e.g. `[Prestamo.DetalleCuotas][NroCuota=1].Fecha`).
- Calculated fields flagged with `PersistentAlias` are server-side expressions; they behave read-only but can be retrieved just like regular fields.
- Many `decimal` fields store monetary amounts in pesos. The suffix `FT` (for "Financial Tracking") often denotes management-only metrics; prefer the base property when both exist.
- Boolean flags such as `ProcesoDebitoPendiente`, `Cuota0`, `DevengaInteresHoyFT` are useful in criteria (e.g. `[ProcesoDebitoPendiente] = True`).
- IDs are integers even when hidden in the UI. They are useful for joins (e.g. `[Prestamo.ID] IN (...)`).
- For collections returned as arrays (`EvaluateList`), remember to order `campos` to match the sequence you need to deserialize.

Use this reference together with the refreshed API guide to design queries that stay within the Evaluate payload limits while still pulling the business context required by downstream agents.
