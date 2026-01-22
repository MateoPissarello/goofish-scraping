"""Utilidad para contar filas OK/ERROR en un CSV de scraping."""

import argparse
from pathlib import Path

import pandas as pd


def count_scraped(csv_path: Path, error_field: str) -> tuple[int, int]:
    """Cuenta cuántas filas están OK y cuántas tienen error.

    Args:
        csv_path (Path): Ruta al CSV de salida del scraping.
        error_field (str): Columna que indica error.

    Returns:
        tuple[int, int]: (total, ok).
    """
    df = pd.read_csv(csv_path)
    total = len(df)
    ok_mask = df[error_field].isna() | (df[error_field].astype(str).str.strip() == "")
    ok = int(ok_mask.sum())
    return total, ok


def main() -> None:
    """CLI para reportar conteos de scraping."""
    parser = argparse.ArgumentParser(
        description="Cuenta cuantas filas fueron scrapeadas sin error.",
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="CSV de salida del scraping.",
    )
    parser.add_argument(
        "--error-field",
        default="ERROR",
        help="Nombre de la columna que indica error.",
    )
    args = parser.parse_args()

    total, ok = count_scraped(args.input, args.error_field)
    print(f"Total filas: {total}")
    print(f"Sin error: {ok}")
    print(f"Con error: {total - ok}")


if __name__ == "__main__":
    main()
