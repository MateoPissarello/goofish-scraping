from utils.CookieManager import CookieManager
from worker.scraping.scraping_repository import get_fresh_cookies


class PdpScrapper:
    def __init__(self, url: str):
        self.cookie_mgr = CookieManager(get_fresh_cookies, use_proxy=False)
