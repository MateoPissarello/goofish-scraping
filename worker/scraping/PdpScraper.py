"""Wrapper simple para scraping de un PDP con caché de cookies."""

from ..utils.CookieManager import CookieManager
from worker.scraping.scraping_repository import get_fresh_cookies
from worker.scraping.scraping_repository import scrape_one


class PdpScrapper:
    """Scraper de PDP con CookieManager compartido."""

    def __init__(
        self,
    ):
        """Inicializa el scraper con un CookieManager compartido."""
        self.cookie_mgr = CookieManager(get_fresh_cookies, use_proxy=True)

    async def scrape(self, url: str):
        """Scrapea una URL y devuelve datos normalizados o error.

        Args:
            url (str): URL del producto.

        Returns:
            dict: Datos normalizados del producto o un diccionario de error.
        """
        try:
            data = await scrape_one(url, cookie_mgr=self.cookie_mgr, timeout_s=15.0)
        except Exception as e:
            return {"URL": url, "ERROR": str(e)}
        return data
