from ..utils.CookieManager import CookieManager
from worker.scraping.scraping_repository import get_fresh_cookies
from worker.scraping.scraping_repository import scrape_one


class PdpScrapper:
    def __init__(
        self,
    ):
        self.cookie_mgr = CookieManager(get_fresh_cookies, use_proxy=True)

    async def scrape(self, url: str):
        try:
            data = await scrape_one(url, cookie_mgr=self.cookie_mgr, timeout_s=15.0)
        except Exception as e:
            return {"URL": url, "ERROR": str(e)}
        return data
