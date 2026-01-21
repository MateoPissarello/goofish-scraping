import argparse
import asyncio
import csv
import json
from pathlib import Path

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


class CookieManager:
    def __init__(self, use_proxy: bool):
        self.use_proxy = use_proxy
        self._cookies = None
        self._lock = asyncio.Lock()

    async def ensure(self, url: str) -> dict:
        if self._cookies is None:
            async with self._lock:
                if self._cookies is None:
                    self._cookies = await get_fresh_cookies(url, use_proxy=self.use_proxy)
        return self._cookies

    async def refresh(self, url: str) -> dict:
        async with self._lock:
            self._cookies = await get_fresh_cookies(url, use_proxy=self.use_proxy)
        return self._cookies


async def scrape_one(
    url: str,
    cookie_mgr: CookieManager,
    retries: int,
) -> dict:
    last_ret = ""
    for _ in range(retries + 1):
        cookies = await cookie_mgr.ensure(url)
        result = await scrape_pdp(url, save_to_file=False, cookies=cookies, use_proxy=cookie_mgr.use_proxy)
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
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        urls = []
        for row in reader:
            url = (row.get("URL") or "").strip()
            if url:
                urls.append(url)
    return urls


def build_row(data: dict) -> dict:
    row = {key: "" for key in OUTPUT_FIELDS}
    row.update({key: value for key, value in data.items() if key in row})
    return row


def split_chunks(urls: list[str], chunk_size: int) -> list[list[str]]:
    if chunk_size <= 0:
        return [urls]
    return [urls[i : i + chunk_size] for i in range(0, len(urls), chunk_size)]


async def run(
    input_path: Path,
    output_path: Path,
    workers: int,
    chunk_size: int,
    retries: int,
    use_proxy: bool,
) -> None:
    urls = load_urls(input_path)
    if not urls:
        print("No se encontraron URLs en el CSV.")
        return

    chunks = split_chunks(urls, chunk_size)
    if not chunks:
        print("No hay URLs para procesar.")
        return

    if workers <= 0:
        workers = 1
    workers = min(workers, len(chunks))

    lock = asyncio.Lock()
    counter_lock = asyncio.Lock()
    counter = {"value": 0}

    queue: asyncio.Queue[list[str]] = asyncio.Queue()
    for chunk in chunks:
        queue.put_nowait(chunk)

    async def worker() -> None:
        cookie_mgr = CookieManager(use_proxy=use_proxy)
        while True:
            try:
                chunk = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            for url in chunk:
                data = await scrape_one(url, cookie_mgr, retries)
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
    parser.add_argument("--workers", type=int, default=5, help="Cantidad de workers (chunks en paralelo)")
    parser.add_argument("--chunk-size", type=int, default=10000, help="Cantidad de URLs por worker")
    parser.add_argument("--retries", type=int, default=1, help="Reintentos por URL si falla el token")
    parser.add_argument("--use-proxy", action="store_true", help="Usar proxy al refrescar cookies")
    args = parser.parse_args()

    asyncio.run(
        run(
            input_path=Path(args.input),
            output_path=Path(args.output),
            workers=args.workers,
            chunk_size=args.chunk_size,
            retries=args.retries,
            use_proxy=args.use_proxy,
        )
    )
