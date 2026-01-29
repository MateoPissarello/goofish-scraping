import asyncio
import json
import logging
import os
import time
from hashlib import md5
from urllib.parse import parse_qs, urlparse

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"
APP_KEY = "34839810"

TEST_URL = "https://www.goofish.com/item?id=894551126004"


def _build_proxy_settings(use_proxy: bool) -> tuple[dict | None, str | None]:
    """Construye configuración de proxy para httpx.

    Args:
        use_proxy (bool): Indica si se debe construir configuración de proxy.

    Returns:
        tuple[dict | None, str | None]: (proxy_settings, proxy_url). Ambos None si no se usa proxy.

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


def extract_item_id(url: str) -> str:
    """Extrae el item_id desde el querystring de la URL.

    Args:
        url (str): URL del producto de Goofish.

    Returns:
        str: Valor del parámetro "id".

    Raises:
        ValueError: Si la URL no contiene el parámetro "id".
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if "id" not in qs:
        raise ValueError("URL sin parametro 'id'")
    return qs["id"][0]


def generate_sign(token: str, timestamp: str, data: str) -> str:
    """Genera la firma MD5 requerida por el endpoint mtop.

    Args:
        token (str): Token de cookies (_m_h5_tk) para firmar.
        timestamp (str): Timestamp en milisegundos.
        data (str): JSON serializado que se envía al endpoint.

    Returns:
        str: Hash MD5 con la firma requerida por el API.
    """
    token_val = token.split("_")[0] if token else ""
    raw = f"{token_val}&{timestamp}&{APP_KEY}&{data}"
    return md5(raw.encode("utf-8")).hexdigest()


async def get_fresh_cookies_V2(target_url: str, use_proxy: bool = False, cookies: dict = None) -> list[dict[str, str]]:
    """Abre un navegador stealth y devuelve cookies útiles para Goofish.

    Args:
        cookie_gen_url (str): URL que se visita para generar cookies.
        use_proxy (bool): Indica si se usa proxy en el navegador.

    Returns:
        dict: Cookies obtenidas desde el navegador.
    """
    logger.info("Obteniendo cookies frescas con una petición...")
    proxy_settings, _ = _build_proxy_settings(use_proxy)
    if cookies is None:
        logger.warning("No se proporcionaron cookies,")
        return RuntimeError("No se proporcionaron cookies")

    item_id = extract_item_id(target_url)
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
            logger.error("Connect timeout al solicitar %s: %s", target_url, exc)
            return {"ret": ["CONNECT_TIMEOUT"], "data": {}, "URL": target_url}
        except httpx.ReadTimeout as exc:
            logger.error("Read timeout al solicitar %s: %s", target_url, exc)
            return {"ret": ["READ_TIMEOUT"], "data": {}, "URL": target_url}
        except httpx.RequestError as exc:
            logger.error("Error de red al solicitar %s: %s", target_url, exc)
            return {"ret": [f"REQUEST_ERROR::{exc.__class__.__name__}"], "data": {}, "URL": target_url}

    result = response.json()
    ret_message = result.get("ret", ["No ret"])[0]
    logger.info("Estado de la respuesta: %s", ret_message)

    response_cookies = [{"name": name, "value": value} for name, value in response.cookies.items()]
    logger.info("Cookies generadas por la respuesta: %d", len(response_cookies))

    return response_cookies


async def main():
    logging.basicConfig(level=logging.INFO)
    cookies = await get_fresh_cookies_V2(TEST_URL, use_proxy=False, cookies={})
    print(cookies)


if __name__ == "__main__":
    asyncio.run(main())
