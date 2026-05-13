from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .guard import run_guard


def main() -> None:
    parser = argparse.ArgumentParser(description="Mantiene una cuenta Coinag por encima de un saldo minimo.")
    parser.add_argument("--env-file", type=Path, help="Archivo KEY=VALUE con configuracion.")
    args = parser.parse_args()

    config = load_config(args.env_file)
    result = run_guard(config)
    print(f"{result.event}: {result.message}")


if __name__ == "__main__":
    main()
