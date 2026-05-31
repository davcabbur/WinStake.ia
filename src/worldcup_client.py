"""
WinStake.ia — Cliente de la World Cup API (api.worldcupapi.com)
Cubre los 13 endpoints. Free trial con tope de 1500 requests → caché agresiva.
Sin modo mock: si falta la key o falla la API, devuelve None y loggea.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from typing import Optional

import config
from src.cache import APICache

logger = logging.getLogger(__name__)


def _create_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Crea una sesión HTTP con retry y backoff exponencial."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class WorldCupClient:
    """Cliente para la World Cup API (api.worldcupapi.com)."""

    def __init__(self, api_key: str = None, lang: str = None):
        self.api_key = config.WORLD_CUP_API_KEY if api_key is None else api_key
        self.lang = lang if lang is not None else config.WORLD_CUP_LANG
        self.base_url = config.WORLD_CUP_API_BASE
        self.cache = APICache()
        self.session = _create_session()

        if not self.api_key:
            logger.warning("⚠️  WORLD_CUP_API_KEY no configurada. Las llamadas devolverán None.")

    def _request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Realiza una petición GET. Inyecta key y lang automáticamente."""
        full_params = {"key": self.api_key, "lang": self.lang, **params}
        try:
            url = f"{self.base_url}/{endpoint}"
            response = self.session.get(url, params=full_params, timeout=15)
            response.raise_for_status()
            remaining = response.headers.get("x-requests-remaining", "?")
            logger.info(f"✅ World Cup API /{endpoint} — requests restantes: {remaining}")
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ World Cup API HTTP error en /{endpoint}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ World Cup API connection error en /{endpoint}: {e}")
            return None
        except ValueError as e:  # JSON inválido
            logger.error(f"❌ World Cup API JSON inválido en /{endpoint}: {e}")
            return None

    def _cached_get(self, endpoint: str, params: dict, ttl: int, cache_key: str):
        """Flujo común: key vacía → None; caché → _request → cache.set."""
        if not self.api_key:
            return None
        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            logger.info(f"✅ /{endpoint} desde caché — 0 requests")
            return cached
        data = self._request(endpoint, params)
        if data is None:
            return None
        self.cache.set(cache_key, data)
        return data

    def get_livescores(self):
        """Marcadores en vivo. GET /livescores."""
        return self._cached_get(
            "livescores", {}, config.CACHE_TTL_WC_LIVE,
            f"wc_livescores_{self.lang}",
        )
