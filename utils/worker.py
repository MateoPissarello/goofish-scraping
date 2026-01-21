import asyncio
from get_cookies import get_fresh_cookies
from PdpHandler import PdpHandler


class ScrapeWorker:
    def __init__(self, proxy):
        self.proxy = proxy
        self.cookies = None

    def init_session(self, url, timeout=60.0):
        self.cookies = asyncio.run(asyncio.wait_for(get_fresh_cookies(url, self.proxy), timeout=timeout))

    def scrape_item(self, url):
        if not self.cookies:
            self.init_session(url)

        handler = PdpHandler(
            url=url,
            cookies=self.cookies,
            proxies={
                "http": f"http://{self.proxy['user']}:{self.proxy['pass']}@{self.proxy['server']}",
                "https": f"http://{self.proxy['user']}:{self.proxy['pass']}@{self.proxy['server']}",
            },
        )

        data = handler.scrape()

        if "ERROR" in data or data.get("ERROR"):
            print("Token inválido, regenerando cookies...")
            self.init_session(url)
            handler = PdpHandler(
                url=url,
                cookies=self.cookies,
                proxies={
                    "http": f"http://{self.proxy['user']}:{self.proxy['pass']}@{self.proxy['server']}",
                    "https": f"http://{self.proxy['user']}:{self.proxy['pass']}@{self.proxy['server']}",
                },
            )
            return handler.scrape()

        return data
