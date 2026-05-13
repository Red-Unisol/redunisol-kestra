#!/usr/bin/env python3
"""Tkinter GUI wrapper around the ARC export generator."""
from __future__ import annotations

import datetime as _dt
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import (
    ExportResult,
    generate_report,
    month_end_for_parts,
)


MONTH_CHOICES = [
    ("Enero", 1),
    ("Febrero", 2),
    ("Marzo", 3),
    ("Abril", 4),
    ("Mayo", 5),
    ("Junio", 6),
    ("Julio", 7),
    ("Agosto", 8),
    ("Septiembre", 9),
    ("Octubre", 10),
    ("Noviembre", 11),
    ("Diciembre", 12),
]
MONTH_NAME_TO_NUMBER = {name: number for name, number in MONTH_CHOICES}
MONTH_DISPLAY = [name for name, _ in MONTH_CHOICES]




class ExportApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Exportar Bancor")
        self.geometry("520x350")
        self.resizable(True, False)

        default_excel = Path("example-input.xlsx").resolve()
        default_output = Path("output").resolve()

        today = _dt.date.today()
        self._current_year = today.year
        default_month_name = MONTH_DISPLAY[today.month - 1]
        self._month_var = tk.StringVar(value=default_month_name)
        self._excel_path_var = tk.StringVar(value=str(default_excel))
        self._output_dir_var = tk.StringVar(value=str(default_output))
        self._arrastre_var = tk.BooleanVar(value=False)
        self._club_mutual_var = tk.BooleanVar(value=False)
        self._status_var = tk.StringVar(value="Listo para generar el reporte.")
        self._progress_var = tk.DoubleVar(value=0.0)

        self._running = False

        self._build_widgets()

    def _build_widgets(self) -> None:
        self.columnconfigure(0, weight=1)

        frame = ttk.Frame(self, padding=20)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Cobros mes pasado:").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
        excel_entry = ttk.Entry(frame, textvariable=self._excel_path_var, width=46)
        excel_entry.grid(row=0, column=1, sticky="ew", pady=(0, 6))
        ttk.Button(frame, text="Examinar...", command=self._choose_excel).grid(row=0, column=2, padx=(10, 0), pady=(0, 6))

        ttk.Label(frame, text="Carpeta destino:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=6)
        output_entry = ttk.Entry(frame, textvariable=self._output_dir_var, width=46)
        output_entry.grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(frame, text="Seleccionar...", command=self._choose_output_dir).grid(row=1, column=2, padx=(10, 0), pady=6)

        ttk.Label(frame, text="Mes a procesar:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=6)
        self._month_combo = ttk.Combobox(frame, values=MONTH_DISPLAY, textvariable=self._month_var, state="readonly", width=20)
        self._month_combo.grid(row=2, column=1, sticky="w", pady=6)
        ttk.Checkbutton(frame, text="Arrastre (CAJA40 0/50/60/90)", variable=self._arrastre_var).grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )
        ttk.Checkbutton(
            frame,
            text="Club Mutual (solo LINEAS CLUB MUTUAL, shot minimo 11000)",
            variable=self._club_mutual_var,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self._button = ttk.Button(frame, text="Generar reporte", command=self._start_export)
        self._button.grid(row=5, column=0, columnspan=3, pady=(12, 12))

        self._progress = ttk.Progressbar(
            frame,
            variable=self._progress_var,
            maximum=100,
            mode="determinate",
        )
        self._progress.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        self._status_label = ttk.Label(frame, textvariable=self._status_var, wraplength=440, justify="center")
        self._status_label.grid(row=7, column=0, columnspan=3, pady=(4, 0))

    def _choose_excel(self) -> None:
        initialdir = Path(self._excel_path_var.get()).expanduser().parent
        path = filedialog.askopenfilename(
            title="Seleccionar archivo Excel",
            filetypes=[("Archivos de Excel", "*.xlsx *.xlsm"), ("Todos los archivos", "*.*")],
            initialdir=initialdir,
        )
        if path:
            self._excel_path_var.set(path)

    def _choose_output_dir(self) -> None:
        initialdir = Path(self._output_dir_var.get()).expanduser()
        directory = filedialog.askdirectory(title="Seleccionar carpeta destino", initialdir=initialdir)
        if directory:
            self._output_dir_var.set(directory)

    def _start_export(self) -> None:
        if self._running:
            return

        excel_path = Path(self._excel_path_var.get()).expanduser()
        output_dir = Path(self._output_dir_var.get()).expanduser()

        month_name = self._month_var.get().strip()
        month_number = MONTH_NAME_TO_NUMBER.get(month_name)
        if month_number is None:
            messagebox.showerror("Mes inválido", "Seleccione un mes válido para el reporte.", parent=self)
            return

        report_date = month_end_for_parts(self._current_year, month_number)

        if not excel_path.exists():
            messagebox.showerror("Archivo no encontrado", f"No se encontro el archivo:\n{excel_path}", parent=self)
            return

        self._running = True
        self._button.config(state=tk.DISABLED)
        self._progress_var.set(0.0)
        self._status_var.set("Iniciando generacion...")

        worker = threading.Thread(
            target=self._run_export,
            args=(report_date, excel_path, output_dir),
            daemon=True,
        )
        worker.start()

    def _run_export(
        self,
        report_date: _dt.date,
        excel_path: Path,
        output_dir: Path,
    ) -> None:
        def progress_cb(fraction: float, message: str) -> None:
            self.after(0, lambda: self._update_progress(fraction, message))

        try:
            result = generate_report(
                report_date=report_date,
                input_excel=excel_path,
                output_dir=output_dir,
                dev_mode=False,
                arrastre_mode=self._arrastre_var.get(),
                club_mutual_mode=self._club_mutual_var.get(),
                progress_callback=progress_cb,
            )
        except Exception as exc:
            self.after(0, lambda: self._handle_failure(exc))
        else:
            self.after(0, lambda: self._handle_success(result))

    def _update_progress(self, fraction: float, message: str) -> None:
        self._progress_var.set(max(0.0, min(fraction, 1.0)) * 100.0)
        self._status_var.set(message)

    def _handle_success(self, result: ExportResult) -> None:
        self._running = False
        self._button.config(state=tk.NORMAL)
        self._update_progress(1.0, "Exportacion completada.")

        base_files = result.base_files
        lines = [f"{category}: {info.path}" for category, info in sorted(result.files.items())]
        summary = "\n".join(lines)
        message = (
            f"Se generaron {result.total_rows} registros distribuidos en {len(base_files)} archivos:\n"
            f"{summary}"
        )
        if result.discarded_log:
            message += f"\n\nPlanillas descartadas registradas en:\n{result.discarded_log}"
        message += f"\n\nRespuesta EvaluateList guardada en:\n{result.api_response_path}"
        messagebox.showinfo("Reporte generado", message, parent=self)

    def _handle_failure(self, exc: Exception) -> None:
        self._running = False
        self._button.config(state=tk.NORMAL)
        self._status_var.set("Ocurrio un error.")
        self._progress_var.set(0.0)
        messagebox.showerror("Error al generar", f"No se pudo generar el reporte:\n{exc}", parent=self)


def main() -> None:
    app = ExportApp()
    app.mainloop()


if __name__ == "__main__":
    main()
