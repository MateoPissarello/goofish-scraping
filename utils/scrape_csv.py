import argparse
import asyncio
import csv
import json
from pathlib import Path

from CookieManager import CookieManager
from scraping import get_fresh_cookies, parse_product, scrape_pdp

TOKEN_ERRORS = ("FAIL_SYS_TOKEN", "TOKEN_EMPTY", "RGV587_ERROR")
OUTPUT_FIELDS = [
    "ITEM_ID",
    "CATEGORY_ID",
    "TITLE",
    "IMAGES",
    "SOLD_PRICE",
    "BROWSE_COUNT",
    "WANT_COUNT",
    "COLLECT_COUNT",
    "QUANTITY",
    "GMT_CREATE",
    "SELLER_ID",
    "URL",
    "ERROR",
]


async def scrape_one(
    url: str,
    cookie_mgr: CookieManager,
    retries: int,
    timeout_s: float,
) -> dict:
    """Scrapea una URL con reintentos y manejo de tokens.

    Args:
        url: URL del producto.
        cookie_mgr: Gestor de cookies para la sesion.
        retries: Reintentos cuando falla el token.
        timeout_s: Timeout maximo por request.

    Returns:
        Diccionario con datos del producto o un error.
    """
    last_ret = ""
    for _ in range(retries + 1):
        cookies = await cookie_mgr.ensure(url)
        try:
            result = await asyncio.wait_for(
                scrape_pdp(
                    url,
                    save_to_file=False,
                    cookies=cookies,
                    use_proxy=cookie_mgr.use_proxy,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            return {"URL": url, "ERROR": "REQUEST_TIMEOUT"}
        ret = result.get("ret", [""])[0]
        last_ret = ret

        if ret and "SUCCESS" not in ret:
            if any(err in ret for err in TOKEN_ERRORS):
                await cookie_mgr.refresh(url)
                continue
            return {"URL": url, "ERROR": ret}

        parsed = await parse_product(result)
        parsed["URL"] = url
        if isinstance(parsed.get("IMAGES"), list):
            parsed["IMAGES"] = json.dumps(parsed["IMAGES"], ensure_ascii=False)
        return parsed

    return {"URL": url, "ERROR": last_ret or "UNKNOWN_ERROR"}


def load_urls(csv_path: Path) -> list[str]:
    """Lee URLs desde un CSV con columna URL.

    Args:
        csv_path: Ruta al CSV de entrada.

    Returns:
        Lista de URLs encontradas.
    """
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        urls = []
        for row in reader:
            url = (row.get("URL") or "").strip()
            if url:
                urls.append(url)
    return urls


def build_row(data: dict) -> dict:
    """Construye una fila completa con todas las columnas esperadas.

    Args:
        data: Datos parciales del producto.

    Returns:
        Diccionario con todas las columnas definidas en OUTPUT_FIELDS.
    """
    row = {key: "" for key in OUTPUT_FIELDS}
    row.update({key: value for key, value in data.items() if key in row})
    return row


async def run(
    input_path: Path,
    output_path: Path,
    workers: int,
    retries: int,
    use_proxy: bool,
    timeout_s: float,
) -> None:
    """Orquesta el scraping concurrente por URLs y genera el CSV.

    Args:
        input_path: Ruta del CSV de entrada.
        output_path: Ruta del CSV de salida.
        workers: Cantidad de workers en paralelo.
        retries: Reintentos por URL si falla el token.
        use_proxy: Indica si se usa proxy al obtener cookies.
        timeout_s: Timeout maximo por URL.
    """
    urls = load_urls(input_path)
    if not urls:
        print("No se encontraron URLs en el CSV.")
        return

    if workers <= 0:
        workers = 1
    workers = min(workers, len(urls))

    lock = asyncio.Lock()
    visited_lock = asyncio.Lock()
    visited: set[str] = set()
    counter_lock = asyncio.Lock()
    counter = {"value": 0}

    queue: asyncio.Queue[str] = asyncio.Queue()
    for url in urls:
        queue.put_nowait(url)

    async def worker() -> None:
        cookie_mgr = CookieManager(get_fresh_cookies, use_proxy=use_proxy)
        while True:
            try:
                url = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            async with visited_lock:
                if url in visited:
                    data = {"URL": url, "ERROR": "DUPLICATE_URL"}
                    row = build_row(data)
                    async with lock:
                        writer.writerow(row)
                        output_file.flush()
                    async with counter_lock:
                        counter["value"] += 1
                        current = counter["value"]
                    print(f"[{current}/{len(urls)}] SKIP - {url} (duplicate)")
                    queue.task_done()
                    continue
                visited.add(url)
            try:
                data = await scrape_one(url, cookie_mgr, retries, timeout_s)
            except Exception as exc:
                data = {"URL": url, "ERROR": f"EXCEPTION::{exc.__class__.__name__}"}
            row = build_row(data)
            async with lock:
                writer.writerow(row)
                output_file.flush()
            async with counter_lock:
                counter["value"] += 1
                current = counter["value"]
            status = "ERROR" if data.get("ERROR") else "OK"
            print(f"[{current}/{len(urls)}] {status} - {data.get('URL')}")
            queue.task_done()

    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        tasks = [asyncio.create_task(worker()) for _ in range(workers)]
        await asyncio.gather(*tasks)

    print(f"CSV generado en: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper paralelo para URLs de Goofish en CSV.")
    parser.add_argument("--input", default="../data/goofish_urls.csv", help="CSV de entrada con columna URL")
    parser.add_argument("--output", default="../data/goofish_products.csv", help="CSV de salida con datos completos")
    parser.add_argument("--workers", type=int, default=5, help="Cantidad de workers en paralelo")
    parser.add_argument("--retries", type=int, default=1, help="Reintentos por URL si falla el token")
    parser.add_argument("--timeout", type=float, default=45.0, help="Timeout maximo por request en segundos")
    parser.add_argument("--use-proxy", action="store_true", help="Usar proxy al refrescar cookies")
    args = parser.parse_args()

    asyncio.run(
        run(
            input_path=Path(args.input),
            output_path=Path(args.output),
            workers=args.workers,
            retries=args.retries,
            use_proxy=args.use_proxy,
            timeout_s=args.timeout,
        )
    )
