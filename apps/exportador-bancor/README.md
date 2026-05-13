# Exportador Bancor

Snapshot limpio del exportador ARC Bancor incorporado a la monorepo.

Este app preserva el comportamiento canónico del script legacy:

- consume cuotas desde `EvaluateList`
- cruza esas cuotas con una planilla Excel mensual de intentos
- consolida por planilla
- clasifica cada planilla
- genera `a-enviar.xlsx`, `bancor-pero-no-enviamos.xlsx`, `posiblemente-bancor.xlsx`, `no-bancor.xlsx` y `reporte.xlsx`

## Alcance de este snapshot

Incluye:

- código fuente Python
- tests unitarios del core
- wrappers CLI y GUI compatibles con el flujo legado
- documentación API relevante
- proceso de build estandarizado con `pyproject.toml` y `build-package.ps1`

Queda deliberadamente afuera:

- el `.git` anidado del repo legacy
- `build/`, `dist/`, `output/` y otros artefactos generados
- dumps operativos viejos que no reflejan el esquema actual del API
- archivos internos de agente que no forman parte del producto

## Estructura

```text
apps/exportador-bancor/
  src/exportador_bancor/
    core.py
    cli.py
    gui.py
  tests/
  docs/api/
  packaging/pyinstaller/
  build-package.ps1
  pyproject.toml
  generate_arc_export.py
  arc_export_gui.py
```

## Dependencias

Runtime:

- `requests`
- `pandas`
- `openpyxl`

Build:

- `pyinstaller`

Todo queda declarado en `pyproject.toml`.

## Instalar localmente

```powershell
python -m pip install -e .
```

Para instalar también lo necesario para empaquetar:

```powershell
python -m pip install -e .[build]
```

## Ejecutar

CLI:

```powershell
python generate_arc_export.py --help
```

GUI:

```powershell
python arc_export_gui.py
```

También se puede usar la instalación editable:

```powershell
exportador-bancor --help
exportador-bancor-gui
```

## Tests

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Build estandarizado

El build local del `.exe` queda centralizado en:

```powershell
.\build-package.ps1
```

El script:

- crea una virtualenv local de build en `.package-venv/`
- instala el proyecto con extras de build
- corre tests
- ejecuta PyInstaller
- arma un paquete zip dentro de `dist/`

Salida esperada:

- `dist/pyinstaller/Exportador Bancor.exe`
- `dist/exportador-bancor-<version>-windows-x86_64.zip`

Si querés saltear tests durante el empaquetado:

```powershell
.\build-package.ps1 -SkipTests
```

## Comportamiento canónico actual

### API

- endpoint: `https://celesol.dyndns.org:5050/api/Empresa/EvaluateList`
- TLS sin CA confiable: el cliente usa `verify=False`
- filtro base: cuotas con saldo positivo dentro de `LINEAS CBU BANCOS VARIOS`
- modo `--club-mutual`: usa `LINEAS CLUB MUTUAL` y filtra defensivamente por esa línea superior aun con filtros custom o dumps amplios

### Excel de entrada

Columnas requeridas:

- `planilla`
- `respuesta`
- `importe`

### Clasificación

La lógica real vive en `src/exportador_bancor/core.py` y hoy funciona así:

- `posiblemente-bancor` para CBU vacío, `000*` o `Revisar CBU`
- `no-bancor` para CBU fuera de regla
- `bancor-pero-no-enviamos` para respuestas prohibidas, planillas viejas sin intentos o sin monto subdivisible
- `a-enviar` para planillas aprobadas con shots calculados

Importante:

- `--arrastre` no genera un workbook aparte
- `--arrastre` cambia qué valores de `CAJA40` son elegibles para `a-enviar`
- `--club-mutual` no cambia las demás clasificaciones; solo ajusta la línea superior consultada y las reglas de shots
- en `--club-mutual` no hay tope superior de shot y el piso operativo pasa a `11000`

## Documentación importada

- `docs/api/API_Usage_Guide.md`
- `docs/api/BOModel_API_Reference.md`
- `docs/api/swagger.json`

Esa documentación sirve como referencia del API, pero la fuente de verdad operativa para este snapshot es el código.
