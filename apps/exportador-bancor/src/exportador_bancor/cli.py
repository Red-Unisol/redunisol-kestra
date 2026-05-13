#!/usr/bin/env python3
"""CLI entry point to generate the ARC export workbooks."""
from __future__ import annotations

import argparse
import datetime as _dt
from pathlib import Path
from typing import Optional

from .core import MAX_ROWS, ExportResult, generate_report


def _parse_report_date(value: Optional[str]) -> Optional[_dt.date]:
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(value)
    except ValueError as err:  # pragma: no cover - input validation
        raise argparse.ArgumentTypeError(f"Invalid date format (expected YYYY-MM-DD): {value}") from err


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate ARC export workbooks.")
    parser.add_argument("--report-date", type=_parse_report_date, default=None, help="Fecha de cobro (YYYY-MM-DD).")
    parser.add_argument(
        "--filter",
        dest="filter_expr",
        default=None,
        help="Expresion de filtro EvaluateList (por defecto se usa el último día del mes seleccionado).",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=MAX_ROWS,
        help=f"Maximo de filas a solicitar al API (default {MAX_ROWS}).",
    )
    parser.add_argument(
        "--input-excel",
        type=Path,
        default=Path("example-input.xlsx"),
        help="Archivo Excel con los intentos del mes anterior.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directorio destino para los archivos generados.",
    )
    parser.add_argument(
        "--dev-mode",
        action="store_true",
        help="Activa logging de planillas no-bancor y mensajes detallados.",
    )
    parser.add_argument(
        "--api-dump",
        type=Path,
        default=None,
        help="Archivo JSON/TXT con una respuesta EvaluateList almacenada (modo offline).",
    )
    parser.add_argument(
        "--arrastre",
        action="store_true",
        help="Habilita el criterio arrastre (CAJA40 en {0,50,60,90, vacío}).",
    )
    parser.add_argument(
        "--club-mutual",
        action="store_true",
        help="Usa LINEAS CLUB MUTUAL y shots sin tope superior con piso de 11000.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suprime mensajes de progreso (solo muestra el resumen final).",
    )
    return parser


def _progress_printer(enabled: bool):
    if not enabled:
        return None

    def _callback(fraction: float, message: str) -> None:
        pct = f"{fraction * 100:5.1f}%"
        print(f"{pct} {message}")

    return _callback


def _print_summary(result: ExportResult) -> None:
    print("Archivos generados:")
    for category, info in sorted(result.files.items()):
        print(f"  - {category:10s}: {info.row_count:5d} filas -> {info.path}")
    if result.discarded_log:
        print(f"Planillas descartadas registradas en {result.discarded_log} ({len(result.discarded_entries)} entradas).")
    print(f"Respuesta EvaluateList guardada en {result.api_response_path}")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = generate_report(
            report_date=args.report_date,
            filter_expr=args.filter_expr,
            max_rows=args.max_rows,
            input_excel=args.input_excel,
            output_dir=args.output_dir,
            dev_mode=args.dev_mode,
            arrastre_mode=args.arrastre,
            club_mutual_mode=args.club_mutual,
            progress_callback=_progress_printer(not args.quiet),
            api_dump_path=args.api_dump,
        )
    except Exception as exc:  # pragma: no cover - thin wrapper
        raise SystemExit(f"Error generating report: {exc}") from exc

    if not args.quiet:
        print()
    _print_summary(result)
    if args.dev_mode and not result.discarded_log:
        print("No se registraron planillas descartadas en esta ejecucion.")


if __name__ == "__main__":
    main()
