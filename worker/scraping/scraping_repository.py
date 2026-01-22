import json
import logging
import time
from hashlib import md5
import os
from dotenv import load_dotenv
from urllib.parse import parse_qs, urlparse
import asyncio
import httpx
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from worker.utils.CookieManager import CookieManager


load_dotenv()
API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"
APP_KEY = "34839810"
TOKEN_ERRORS = ("FAIL_SYS_TOKEN", "TOKEN_EMPTY", "RGV587_ERROR")
TEST_URL = "https://www.goofish.com/item?id=894551126004"


MAX_TOKEN_RETRIES = 2


logger = logging.getLogger(__name__)


def _build_proxy_settings(use_proxy: bool) -> tuple[dict | None, str | None]:
    """Construye configuracion de proxy para Playwright y httpx.

    Args:
        use_proxy: Indica si se debe construir configuracion de proxy.
        proxy_server: URL del servidor proxy.
        proxy_user: Usuario del proxy.
        proxy_pass: Contraseña del proxy.
    Returns:
        Tupla con (proxy_settings, proxy_url). Ambos None si no se usa proxy.

    Raises:
        ValueError: Si faltan variables de entorno del proxy.
    """
    if not use_proxy:
        return None, None
    proxy_server = os.getenv("PROXY_SERVER")
    proxy_user = os.getenv("PROXY_USER")
    proxy_pass = os.getenv("PROXY_PASS")

    if not proxy_server or not proxy_user or not proxy_pass:
        raise ValueError("Falta configurar PROXY_SERVER/PROXY_USER/PROXY_PASS")
    proxy_settings = {
        "server": f"http://{proxy_server}",
        "username": proxy_user,
        "password": proxy_pass,
    }
    proxy_url = f"http://{proxy_user}:{proxy_pass}@{proxy_server}"
    return proxy_settings, proxy_url


async def get_fresh_cookies(target_url: str, use_proxy: bool = False) -> dict:
    """Abre un navegador stealth y devuelve cookies utiles para Goofish.

    Args:
        target_url: URL que se visita para generar cookies.
        use_proxy: Indica si se usa proxy en el navegador.

    Returns:
        Diccionario de cookies obtenidas desde el navegador.
    """
    logger.info("Obteniendo cookies frescas con Playwright...")
    proxy_settings, _ = _build_proxy_settings(use_proxy)

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_settings,
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/143.0.0.0 Safari/537.36"
            )
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
    """Extrae el item_id desde el querystring de la URL.

    Args:
        url: URL del producto de Goofish.

    Returns:
        Valor del parametro "id".

    Raises:
        ValueError: Si la URL no contiene el parametro "id".
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" not in qs:
        raise ValueError("URL sin parametro 'id'")
    return qs["id"][0]


def generate_sign(token: str, timestamp: str, data: str) -> str:
    """Genera la firma MD5 requerida por el endpoint mtop.

    Args:
        token: Token de cookies (_m_h5_tk) para firmar.
        timestamp: Timestamp en milisegundos.
        data: JSON serializado que se envia al endpoint.

    Returns:
        Hash MD5 con la firma requerida por el API.
    """
    token_val = token.split("_")[0] if token else ""
    raw = f"{token_val}&{timestamp}&{APP_KEY}&{data}"
    return md5(raw.encode("utf-8")).hexdigest()


async def scrape_pdp(
    url: str,
    save_to_file: bool = True,
    cookies: dict | None = None,
    use_proxy: bool = False,
) -> dict:
    """Consulta el endpoint de detalle y devuelve el JSON de producto.

    Args:
        url: URL del producto de Goofish.
        save_to_file: Indica si se guarda la respuesta en un archivo local.
        cookies: Cookies a reutilizar en la peticion.
        use_proxy: Indica si se usa proxy en la peticion HTTP.

    Returns:
        Diccionario con el JSON de respuesta del endpoint.
    """
    if cookies is None:
        logger.warning("No se proporcionaron cookies, obteniendo cookies frescas...")
        cookies = await get_fresh_cookies(url, use_proxy=use_proxy)

    item_id = extract_item_id(url)
    payload = {"itemId": item_id}
    data_str = json.dumps(payload, separators=(",", ":"))

    token = cookies.get("_m_h5_tk", "")
    timestamp = str(int(time.time() * 1000))
    sign = generate_sign(token, timestamp, data_str)

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
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/143.0.0.0 Safari/537.36"
        ),
    }

    _, proxy_url = _build_proxy_settings(use_proxy)
    transport = httpx.AsyncHTTPTransport(proxy=proxy_url) if proxy_url else None
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
                content=f"data={data_str}",
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

    result = response.json()
    ret_message = result.get("ret", ["No ret"])[0]
    logger.info("Estado de la respuesta: %s", ret_message)

    if save_to_file:
        filename = f"response_{item_id}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(json.dumps(result, indent=2, ensure_ascii=False))
        logger.info("Resultado guardado en: %s", filename)

    return result


async def parse_product(product: dict) -> dict:
    """Normaliza el payload de Goofish a un esquema plano.

    Args:
        product: Respuesta cruda del endpoint de detalle.

    Returns:
        Diccionario con campos normalizados del producto.
    """
    data = product.get("data", {})
    track = data.get("trackParams", {})
    item = data.get("itemDO", {})
    seller = data.get("sellerDO", {})

    return {
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


async def scrape_one(
    url: str,
    cookie_mgr: CookieManager,
    timeout_s: float,
) -> dict:
    """
    Scrapea una URL con manejo de tokens.
    Los retries de job-level los maneja SQS + DLQ.
    """
    last_ret = ""

    for _ in range(MAX_TOKEN_RETRIES + 1):
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
            raise RuntimeError("REQUEST_TIMEOUT")

        ret = result.get("ret", [""])[0]
        last_ret = ret

        if ret and "SUCCESS" not in ret:
            if any(err in ret for err in TOKEN_ERRORS):
                await cookie_mgr.refresh(url)
                continue

            raise RuntimeError(ret)

        parsed = await parse_product(result)
        parsed["URL"] = url

        if isinstance(parsed.get("IMAGES"), list):
            parsed["IMAGES"] = json.dumps(parsed["IMAGES"], ensure_ascii=False)

        return parsed

    # Si agotamos retries de token → job falla
    raise RuntimeError(last_ret or "TOKEN_RETRY_EXHAUSTED")
