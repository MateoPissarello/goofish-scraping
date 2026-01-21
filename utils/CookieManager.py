import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


class CookieManager:
    """Gestiona cookies en memoria para scraping concurrente.

    Attributes:
        use_proxy: Indica si se usa proxy al obtener cookies.
    """
    def __init__(
        self,
        fetch_cookies: Callable[[str, bool], Awaitable[dict]],
        use_proxy: bool,
    ):
        """Inicializa el gestor con el callback de obtencion de cookies.

        Args:
            fetch_cookies: Funcion async que obtiene cookies para una URL.
            use_proxy: Indica si se usa proxy al obtener cookies.
        """
        self._fetch_cookies = fetch_cookies
        self.use_proxy = use_proxy
        self._cookies = None
        self._lock = asyncio.Lock()

    async def ensure(self, url: str) -> dict:
        """Devuelve cookies existentes o las obtiene una sola vez con lock.

        Args:
            url: URL objetivo usada para obtener cookies si faltan.

        Returns:
            Diccionario de cookies en memoria.
        """
        if self._cookies is None:
            async with self._lock:
                if self._cookies is None:
                    self._cookies = await self._fetch_cookies(url, use_proxy=self.use_proxy)
        return self._cookies

    async def refresh(self, url: str) -> dict:
        """Fuerza la actualizacion de cookies en el cache.

        Args:
            url: URL objetivo usada para obtener cookies nuevas.

        Returns:
            Diccionario de cookies actualizadas.
        """
        async with self._lock:
            logger.info("Refrescando cookies...")
            self._cookies = await self._fetch_cookies(url, use_proxy=self.use_proxy)
        return self._cookies
