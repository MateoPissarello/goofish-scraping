import argparse
import asyncio
import csv
import json
from pathlib import Path

from scraping import get_fresh_cookies, parse_product, scrape_pdp

TOKEN_ERRORS = ("FAIL_SYS_TOKEN", "TOKEN_EMPTY", "RGV587_ERROR")


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
    index: int,
    url: str,
    semaphore: asyncio.Semaphore,
    cookie_mgr: CookieManager,
    retries: int,
) -> tuple[int, dict]:
    async with semaphore:
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
                return index, {"URL": url, "ERROR": ret}

            parsed = await parse_product(result)
            parsed["URL"] = url
            if isinstance(parsed.get("IMAGES"), list):
                parsed["IMAGES"] = json.dumps(parsed["IMAGES"], ensure_ascii=False)
            return index, parsed

        return index, {"URL": url, "ERROR": last_ret or "UNKNOWN_ERROR"}


def load_urls(csv_path: Path) -> tuple[list[str], list[str]]:
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        urls = []
        for row in reader:
            url = (row.get("URL") or "").strip()
            if url:
                urls.append(url)
    return urls, fieldnames


def build_rows(results: list[tuple[int, dict]], fieldnames: list[str]) -> tuple[list[dict], list[str]]:
    if "URL" not in fieldnames:
        fieldnames.append("URL")
    if "ERROR" not in fieldnames:
        fieldnames.append("ERROR")

    empty_row = {name: "" for name in fieldnames}
    rows = []
    for _, data in sorted(results, key=lambda x: x[0]):
        for key in data.keys():
            if key not in empty_row:
                empty_row[key] = ""
                fieldnames.append(key)
        row = empty_row.copy()
        row.update(data)
        rows.append(row)
    return rows, fieldnames


async def run(input_path: Path, output_path: Path, concurrency: int, retries: int, use_proxy: bool) -> None:
    urls, fieldnames = load_urls(input_path)
    if not urls:
        print("No se encontraron URLs en el CSV.")
        return

    cookie_mgr = CookieManager(use_proxy=use_proxy)
    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(scrape_one(i, url, semaphore, cookie_mgr, retries))
        for i, url in enumerate(urls)
    ]

    results = []
    for task in asyncio.as_completed(tasks):
        index, data = await task
        results.append((index, data))
        status = "ERROR" if data.get("ERROR") else "OK"
        print(f"[{index + 1}/{len(urls)}] {status} - {data.get('URL')}")

    rows, fieldnames = build_rows(results, fieldnames)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"CSV generado en: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper paralelo para URLs de Goofish en CSV.")
    parser.add_argument("--input", default="../data/goofish_urls.csv", help="CSV de entrada con columna URL")
    parser.add_argument("--output", default="../data/goofish_products.csv", help="CSV de salida con datos completos")
    parser.add_argument("--concurrency", type=int, default=5, help="Cantidad de scrapes concurrentes")
    parser.add_argument("--retries", type=int, default=1, help="Reintentos por URL si falla el token")
    parser.add_argument("--use-proxy", action="store_true", help="Usar proxy al refrescar cookies")
    args = parser.parse_args()

    asyncio.run(
        run(
            input_path=Path(args.input),
            output_path=Path(args.output),
            concurrency=args.concurrency,
            retries=args.retries,
            use_proxy=args.use_proxy,
        )
    )
