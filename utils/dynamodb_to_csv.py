"""Exporta items de DynamoDB a CSV."""

import argparse
import csv
import json
import os
from decimal import Decimal
from typing import Any

import boto3


def _json_fallback(value: Any) -> Any:
    """Convierte Decimals y estructuras no serializables a tipos JSON."""
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, set):
        return list(value)
    return value


def _normalize_item(item: dict) -> dict:
    """Normaliza un item de DynamoDB para escritura en CSV.

    Args:
        item (dict): Item crudo desde DynamoDB.

    Returns:
        dict: Item con valores serializables.
    """
    return json.loads(json.dumps(item, default=_json_fallback))


def scan_table(table_name: str, region: str | None = None) -> list[dict]:
    """Escanea una tabla completa de DynamoDB y devuelve los items.

    Args:
        table_name (str): Nombre de la tabla.
        region (str | None): Región AWS.

    Returns:
        list[dict]: Lista de items.
    """
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)

    items: list[dict] = []
    scan_kwargs: dict[str, Any] = {}

    while True:
        response = table.scan(**scan_kwargs)
        batch = response.get("Items", [])
        items.extend(_normalize_item(item) for item in batch)
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    return items


def write_csv(items: list[dict], output_path: str, fields: list[str] | None = None) -> None:
    """Escribe items en un CSV.

    Args:
        items (list[dict]): Items ya normalizados.
        output_path (str): Ruta del CSV de salida.
        fields (list[str] | None): Columnas a exportar. Si es None, se usan todas.

    Returns:
        None
    """
    if not items:
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(fields or [])
        return

    if fields is None:
        field_set: set[str] = set()
        for item in items:
            field_set.update(item.keys())
        fields = sorted(field_set)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in items:
            writer.writerow({key: item.get(key, "") for key in fields})


def main() -> None:
    """CLI para exportar DynamoDB a CSV."""
    parser = argparse.ArgumentParser(
        description="Exporta una tabla DynamoDB a CSV.",
    )
    parser.add_argument(
        "--table",
        default=os.getenv("GOOFISH_PARSED_URLS_TABLE"),
        help="Nombre de la tabla DynamoDB (default: env GOOFISH_PARSED_URLS_TABLE).",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Ruta de salida del CSV.",
    )
    parser.add_argument(
        "--region",
        default=os.getenv("AWS_REGION"),
        help="Región AWS (default: env AWS_REGION).",
    )
    parser.add_argument(
        "--fields",
        default="",
        help="Lista de columnas separadas por coma (opcional).",
    )
    args = parser.parse_args()

    if not args.table:
        raise SystemExit("Falta --table o la variable GOOFISH_PARSED_URLS_TABLE")

    fields = [f.strip() for f in args.fields.split(",") if f.strip()] or None

    items = scan_table(args.table, args.region)
    write_csv(items, args.output, fields)
    print(f"Exportados {len(items)} items a {args.output}")


if __name__ == "__main__":
    main()
