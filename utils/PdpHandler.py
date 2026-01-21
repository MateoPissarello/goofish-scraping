import requests
import json
import time
from urllib.parse import urlparse, parse_qs
from hashlib import md5


class PdpHandler:
    API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"
    APP_KEY = "34839810"
    MAX_RETRIES = 3

    def __init__(self, url, cookies: dict, proxies):
        self.url = url
        self.item_id = self._extract_item_id(url)
        self.proxies = proxies
        # Usamos Session para mantener las cookies dinámicas
        self.session = requests.Session()
        self.session.proxies = proxies
        self.session.cookies.update(cookies)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Referer": f"https://www.goofish.com/item?id={self.item_id}",
        }

    def _extract_item_id(self, url) -> str:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "id" not in qs:
            raise ValueError("URL sin id")
        return qs["id"][0]

    def _generate_sign(self, token: str, timestamp: str, data: str) -> str:
        token_val = token.split("_")[0] if token else ""
        raw = f"{token_val}&{timestamp}&{self.APP_KEY}&{data}"
        return md5(raw.encode("utf-8")).hexdigest()

    def _preflight_token(self, data_str: str) -> str:
        timestamp = str(int(time.time() * 1000))
        params = {
            "jsv": "2.7.2",
            "appKey": self.APP_KEY,
            "t": timestamp,
            "sign": "",
            "v": "1.0",
            "type": "originaljson",
            "dataType": "json",
            "api": "mtop.taobao.idle.pc.detail",
            "data": data_str,
        }

        try:
            self.session.get(
                self.API_URL,
                headers=self.headers,
                params=params,
                timeout=15,
            )
        except requests.RequestException:
            return ""

        return self.session.cookies.get("_m_h5_tk", "")

    def fetch_data(self) -> dict:
        payload = {"itemId": self.item_id}
        data_str = json.dumps(payload, separators=(",", ":"))
        last_error = None

        for _ in range(self.MAX_RETRIES):
            token = self.session.cookies.get("_m_h5_tk", "")
            if not token:
                token = self._preflight_token(data_str)

            timestamp = str(int(time.time() * 1000))
            sign = self._generate_sign(token, timestamp, data_str)

            params = {
                "jsv": "2.7.2",
                "appKey": self.APP_KEY,
                "t": timestamp,
                "sign": sign,
                "v": "1.0",
                "type": "originaljson",
                "dataType": "json",
                "api": "mtop.taobao.idle.pc.detail",
                "data": data_str,
            }

            try:
                response = self.session.get(
                    self.API_URL,
                    headers=self.headers,
                    params=params,
                    timeout=15,
                )
                res_json = response.json()
            except (requests.RequestException, ValueError) as exc:
                last_error = str(exc)
                continue

            ret_message = res_json.get("ret", ["No ret"])[0]
            print(f"RESPUESTA SERVIDOR: {ret_message}")

            if "SUCCESS" in ret_message:
                return res_json

            if "FAIL_SYS_TOKEN" in ret_message or "TOKEN_EMPTY" in ret_message:
                last_error = ret_message
                continue

            if "FAIL_SYS_ILLEGAL_ACCESS" in ret_message or "FAIL_SYS_USER_VALIDATE" in ret_message:
                return {"ret": [ret_message], "data": {}}

            last_error = ret_message

        return {"ret": [last_error or "FAIL_SYS_UNKNOWN"], "data": {}}

    def parse_product(self, raw_json: dict) -> dict:
        ret_message = raw_json.get("ret", [""])[0]
        if ret_message and "SUCCESS" not in ret_message:
            return {"ERROR": f"MTOP error: {ret_message}"}

        data = raw_json.get("data", {})
        item = data.get("itemDO", {})
        track = data.get("trackParams", {})

        if not item:
            return {
                "ERROR": "El servidor no devolvió datos del producto. Posible bloqueo por IP/Fingerprint.",
            }

        images = [img.get("photoSearchUrl") for img in item.get("imageInfos", []) if img.get("photoSearchUrl")]

        return {
            "ITEM_ID": track.get("itemId") or self.item_id,
            "TITLE": item.get("title"),
            "PRICE": item.get("price"),
            "IMAGES": images,
            "SOLD_PRICE": item.get("soldPrice"),
            "SELLER_ID": data.get("sellerDO", {}).get("sellerId"),
        }

    def scrape(self) -> dict:
        raw = self.fetch_data()
        return self.parse_product(raw)


if __name__ == "__main__":
    cookies = {
        "_m_h5_tk": "6d3cddbed5d7e39b5ef0337b09a6e2f9_1768955062750",
        "_m_h5_tk_enc": "da1b58ef0c7d052a08ef70fe052f120c",
        "cookie2": "1887efd6a7ab51064b86528b25a39ae8",
        "tfstk": "g3ztEd4dK3c_iFQCeFjhnzXQly5ukMVNpRPWoxDMcJeLg-LMSq0icjMLUADGglDXMveqIc0_sZEYIkumIPqgDkeaNc2Yg1ljh-wxnlfhr5PZuq6okabu_oLAglztlKVI7j0Ff2Vdr5PZuWaOxUblkSgExmMbhh9BdvlrhqM6l6HIMb-XC-gf96hrNEGXlfgIdbkIhqgbhW1KgvGjlqwbO6h2h_BtpCMDkljfqlpy5q8XlyhtA4VsCnH3JfntF5tDlEtI6cH71vW9rMjS2RiYu_LLprHxmYowN3nUfWUx4r76RW0ZB0GUYtKxeoNg4uaciEH7VSasXk7vRVIrMz4JDfJoejxO9rt20cGeJgJY-EnU7HGKE1390noFTXHl96K20cGE9Yft6n-qYP5..-Que-B4BKotleZDuuRw_5PNHejGuC_T5hZW29KcoE4XnnsvvTvAlKLxmnCR9-pXhKn4D1BioqBvknSRpnpYH-9f0gBJDKeYhKsvA-6fruCtuMR8Er7UQ5HpGZKun7tdymU49320luQk6I_Ai-2b2a3Q2Xj6VLeSh6M8Hu74hwO9vxg5YLVJlf1BDinGIRs5feN8l78uWGh51fUQg3VvFqTBw_TSyVvdmJj_d4vmHq2O2CSPqJe_gxDEShEoKvn4vgdNWNDnpqId2CSPqvDK0MIJ_a45..",
    }
    proxies = {
        "http": "http://codify-dc-any:58ADAB79s03h8TJ@gw.netnut.net:5959",
        "https": "http://codify-dc-any:58ADAB79s03h8TJ@gw.netnut.net:5959",
    }

    url = "https://www.goofish.com/item?id=995598771021"
    handler = PdpHandler(url, cookies, proxies)
    product = handler.scrape()
    print(json.dumps(product, indent=2, ensure_ascii=False))
