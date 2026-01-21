import asyncio
import logging
import httpx
import json
import time
from hashlib import md5
from urllib.parse import urlparse, parse_qs
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

test_url = "https://www.goofish.com/item?id=894551126004"

# Configuración de la API
API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"
APP_KEY = "34839810"

# Configuración del proxy (opcional)
PROXY_CONFIG = {
    "server": "gw.netnut.net:5959",
    "user": "codify-dc-any",
    "pass": "58ADAB79s03h8TJ",
}

# Cookies (se actualizarán automáticamente)
COOKIES = None
TOKEN_ERRORS = ("FAIL_SYS_TOKEN", "TOKEN_EMPTY", "RGV587_ERROR")
logger = logging.getLogger(__name__)


async def get_fresh_cookies(target_url: str, use_proxy: bool = False) -> dict:
    """
    Obtiene cookies frescas navegando a la página con Playwright.

    Args:
        target_url: URL de la página para obtener cookies
        use_proxy: Si es True, usa el proxy configurado

    Returns:
        dict: Diccionario con las cookies obtenidas
    """
    logger.info("Obteniendo cookies frescas con Playwright...")

    proxy_settings = None
    if use_proxy:
        proxy_settings = {
            "server": f"http://{PROXY_CONFIG['server']}",
            "username": PROXY_CONFIG["user"],
            "password": PROXY_CONFIG["pass"],
        }

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_settings,
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        )

        page = await context.new_page()

        logger.info("Navegando a: %s", target_url)
        await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(2000)

        cookies_list = await context.cookies()
        cookies_dict = {c["name"]: c["value"] for c in cookies_list}

        await browser.close()

        logger.info("Cookies obtenidas: %d cookies", len(cookies_dict))
        logger.info("  - _m_h5_tk: %s", "ok" if "_m_h5_tk" in cookies_dict else "missing")
        logger.info("  - cookie2: %s", "ok" if "cookie2" in cookies_dict else "missing")

        return cookies_dict


def extract_item_id(url: str) -> str:
    """Extrae el item_id de la URL"""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" not in qs:
        raise ValueError("URL sin parámetro 'id'")
    return qs["id"][0]


def generate_sign(token: str, timestamp: str, data: str) -> str:
    """Genera la firma MD5 requerida por la API"""
    token_val = token.split("_")[0] if token else ""
    raw = f"{token_val}&{timestamp}&{APP_KEY}&{data}"
    return md5(raw.encode("utf-8")).hexdigest()


async def scrape_pdp(url: str, save_to_file: bool = True, cookies: dict = None, use_proxy: bool = False):
    """
    Hace scraping de una página de detalle de producto (PDP) de Goofish.

    Args:
        url: URL del producto en formato https://www.goofish.com/item?id=XXXXXX
        save_to_file: Si es True, guarda el resultado en un archivo TXT
        cookies: Diccionario de cookies (si es None, se obtendrán automáticamente)
        use_proxy: Si es True, usa proxy para obtener cookies

    Returns:
        dict: Respuesta JSON de la API
    """
    # Si no se proporcionan cookies, obtenerlas automáticamente
    if cookies is None:
        logger.warning("No se proporcionaron cookies, obteniendo cookies frescas...")
        cookies = await get_fresh_cookies(url, use_proxy=use_proxy)

    # Extraer el item_id de la URL
    item_id = extract_item_id(url)

    # Preparar el payload
    payload = {"itemId": item_id}
    data_str = json.dumps(payload, separators=(",", ":"))

    # Obtener el token de las cookies
    token = cookies.get("_m_h5_tk", "")

    # Generar timestamp y firma
    timestamp = str(int(time.time() * 1000))
    sign = generate_sign(token, timestamp, data_str)

    # Construir parámetros de la URL
    params = {
        "jsv": "2.7.2",
        "appKey": APP_KEY,
        "t": timestamp,
        "sign": sign,
        "v": "1.0",
        "type": "originaljson",
        "accountSite": "xianyu",
        "dataType": "json",
        "timeout": "20000",
        "api": "mtop.taobao.idle.pc.detail",
        "sessionOption": "AutoLoginOnly",
        "spm_cnt": "a21ybx.item.0.0",
    }

    # Construir headers
    headers = {
        "accept": "application/json",
        "accept-language": "es-ES,es;q=0.9",
        "cache-control": "no-cache",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.goofish.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://www.goofish.com/",
        "sec-ch-ua": '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    }

    # Preparar el body como URL encoded
    body_data = f"data={data_str}"

    # Hacer la petición con httpx
    proxy_url = None
    if use_proxy:
        proxy_url = f"http://{PROXY_CONFIG['user']}:{PROXY_CONFIG['pass']}@{PROXY_CONFIG['server']}"

    transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None

    # Timeout más estricto y controlado: si la conexión se cuelga o tarda
    # demasiado, queremos fallar rápido y devolver un error manejable.
    timeout = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=30.0)

    async with httpx.AsyncClient(
        cookies=cookies,
        timeout=timeout,
        transport=transport,
    ) as client:
        try:
            response = await client.post(
                API_URL,
                params=params,
                headers=headers,
                content=body_data,
            )
        except httpx.ConnectTimeout as exc:
            logger.error("Connect timeout al solicitar %s: %s", url, exc)
            return {"ret": ["CONNECT_TIMEOUT"], "data": {}, "URL": url}
        except httpx.ReadTimeout as exc:
            logger.error("Read timeout al solicitar %s: %s", url, exc)
            return {"ret": ["READ_TIMEOUT"], "data": {}, "URL": url}
        except httpx.RequestError as exc:
            logger.error("Error de red al solicitar %s: %s", url, exc)
            return {"ret": [f"REQUEST_ERROR::{exc.__class__.__name__}"], "data": {}, "URL": url}

        # Parsear la respuesta
        result = response.json()

        # Verificar el estado de la respuesta
        ret_message = result.get("ret", ["No ret"])[0]
        logger.info("Estado de la respuesta: %s", ret_message)

        # Guardar el resultado en un archivo TXT
        if save_to_file:
            filename = f"response_{item_id}.txt"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(json.dumps(result, indent=2, ensure_ascii=False))
            logger.info("Resultado guardado en: %s", filename)

        return result


async def parse_product(product: dict):
    data = product.get("data", {})
    track = data.get("trackParams", {})
    item = data.get("itemDO", {})
    seller = data.get("sellerDO", {})

    parsed = {
        "ITEM_ID": track.get("itemId"),
        "CATEGORY_ID": track.get("categoryId"),
        "TITLE": item.get("title"),
        "IMAGES": [img.get("photoSearchUrl") for img in item.get("imageInfos", [])],
        "SOLD_PRICE": item.get("soldPrice"),
        "BROWSE_COUNT": item.get("browseCnt"),
        "WANT_COUNT": item.get("wantCnt"),
        "COLLECT_COUNT": item.get("collectCnt"),
        "QUANTITY": item.get("quantity"),
        "GMT_CREATE": item.get("gmtCreate"),
        "SELLER_ID": seller.get("sellerId"),
    }

    return parsed


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
            logger.info("Refrescando cookies...")
            self._cookies = await get_fresh_cookies(url, use_proxy=self.use_proxy)
        return self._cookies


async def batch_processing(
    urls: list[str],
    concurrency: int = 5,
    retries: int = 1,
    use_proxy: bool = False,
    save_to_file: bool = False,
) -> list[dict]:
    if not urls:
        return []

    cookie_mgr = CookieManager(use_proxy=use_proxy)
    semaphore = asyncio.Semaphore(concurrency)

    async def _worker(index: int, url: str) -> tuple[int, dict]:
        async with semaphore:
            logger.info("Scrape start [%s/%s]: %s", index + 1, len(urls), url)
            last_ret = ""
            for _ in range(retries + 1):
                cookies = await cookie_mgr.ensure(url)
                try:
                    result = await scrape_pdp(
                        url,
                        save_to_file=save_to_file,
                        cookies=cookies,
                        use_proxy=use_proxy,
                    )
                except Exception as exc:  # salvaguarda para que nunca reviente el batch
                    logger.exception("Error inesperado scrapeando %s: %s", url, exc)
                    return index, {"URL": url, "ERROR": f"EXCEPTION::{exc.__class__.__name__}"}
                ret_message = result.get("ret", [""])[0]
                last_ret = ret_message
                if ret_message and "SUCCESS" not in ret_message:
                    if any(err in ret_message for err in TOKEN_ERRORS):
                        logger.warning("Token error, reintentando con cookies nuevas: %s", ret_message)
                        await cookie_mgr.refresh(url)
                        continue
                    logger.error("Scrape error: %s", ret_message)
                    return index, {"URL": url, "ERROR": ret_message}

                parsed = await parse_product(result)
                parsed["URL"] = url
                logger.info("Scrape ok: %s", url)
                return index, parsed

            logger.error("Scrape agotado: %s", url)
            return index, {"URL": url, "ERROR": last_ret or "UNKNOWN_ERROR"}

    tasks = [asyncio.create_task(_worker(i, url)) for i, url in enumerate(urls)]
    results = [await task for task in asyncio.as_completed(tasks)]
    return [data for _, data in sorted(results, key=lambda x: x[0])]


if __name__ == "__main__":
    print("=== Modo automático: Obteniendo cookies frescas ===\n")
    result = asyncio.run(scrape_pdp(test_url, use_proxy=False))

    parsed = asyncio.run(parse_product(result))
    print("\n--- RESULTADO ---")
    print(json.dumps(parsed, indent=2, ensure_ascii=False))
