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

    def _request(self, endpoint: str, params: dict) -> Optional[dict | list]:
        """Realiza una petición GET. Inyecta key y lang automáticamente.

        Devuelve el JSON crudo de la API tal cual (dict o list); el llamante
        es responsable de desempaquetar/normalizar el shape. None en error.
        """
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

    def get_fixtures(self, group=None, team_id=None, date=None):
        """Partidos / calendario. GET /fixtures (group, team_id o date opcionales)."""
        params = {}
        if group is not None:
            params["group"] = group
        if team_id is not None:
            params["team_id"] = team_id
        if date is not None:
            params["date"] = date
        cache_key = f"wc_fixtures_{group}_{team_id}_{date}_{self.lang}"
        return self._cached_get("fixtures", params, config.CACHE_TTL_WC_FIXTURES, cache_key)

    def get_standings(self, group, form=False):
        """Clasificación de grupo. GET /standings (form=1 añade racha)."""
        params = {"group": group}
        if form:
            params["form"] = 1
        cache_key = f"wc_standings_{group}_{int(form)}_{self.lang}"
        return self._cached_get("standings", params, config.CACHE_TTL_WC_STANDINGS, cache_key)

    def get_live_standings(self, group):
        """Clasificación en vivo. GET /livestandings."""
        return self._cached_get(
            "livestandings", {"group": group}, config.CACHE_TTL_WC_LIVE,
            f"wc_livestandings_{group}_{self.lang}",
        )

    def get_commentary(self, match_id, from_=None, to=None):
        """Narración minuto a minuto. GET /commentary (from/to en segundos)."""
        params = {"match_id": match_id}
        if from_ is not None:
            params["from"] = from_
        if to is not None:
            params["to"] = to
        cache_key = f"wc_commentary_{match_id}_{from_}_{to}_{self.lang}"
        return self._cached_get("commentary", params, config.CACHE_TTL_WC_MATCH, cache_key)

    def get_events(self, match_id):
        """Goles, tarjetas y cambios. GET /events."""
        return self._cached_get(
            "events", {"match_id": match_id}, config.CACHE_TTL_WC_MATCH,
            f"wc_events_{match_id}_{self.lang}",
        )

    def get_statistics(self, match_id):
        """Estadísticas del partido. GET /statistics (la API ignora lang aquí)."""
        return self._cached_get(
            "statistics", {"match_id": match_id}, config.CACHE_TTL_WC_MATCH,
            f"wc_statistics_{match_id}_{self.lang}",
        )

    def get_lineups(self, match_id):
        """Alineaciones. GET /lineups."""
        return self._cached_get(
            "lineups", {"match_id": match_id}, config.CACHE_TTL_WC_MATCH,
            f"wc_lineups_{match_id}_{self.lang}",
        )

    def get_squad(self, team_id):
        """Plantilla de una selección. GET /squads."""
        return self._cached_get(
            "squads", {"team_id": team_id}, config.CACHE_TTL_WC_STATIC,
            f"wc_squads_{team_id}_{self.lang}",
        )

    def get_history(self, date_from=None, date_to=None, team_id=None):
        """Partidos finalizados. GET /history (date_from/date_to/team_id opcionales)."""
        params = {}
        if date_from is not None:
            params["date_from"] = date_from
        if date_to is not None:
            params["date_to"] = date_to
        if team_id is not None:
            params["team_id"] = team_id
        cache_key = f"wc_history_{date_from}_{date_to}_{team_id}_{self.lang}"
        return self._cached_get("history", params, config.CACHE_TTL_WC_STATIC, cache_key)

    def get_head2head(self, team1_id, team2_id):
        """Cara a cara histórico entre dos selecciones. GET /head2head."""
        params = {"team1_id": team1_id, "team2_id": team2_id}
        # Cache key normalizada (min/max) — el h2h es simétrico, así (A,B) y (B,A)
        # comparten entrada y no gastan dos requests. Coincide con FootballClient.get_h2h.
        cache_key = f"wc_head2head_{min(team1_id, team2_id)}_{max(team1_id, team2_id)}_{self.lang}"
        return self._cached_get("head2head", params, config.CACHE_TTL_WC_STATIC, cache_key)

    def get_top_scorers(self):
        """Máximos goleadores. GET /goalscorers."""
        return self._cached_get(
            "goalscorers", {}, config.CACHE_TTL_WC_STATIC,
            f"wc_goalscorers_{self.lang}",
        )

    def get_cards(self):
        """Ranking de tarjetas (rojas/amarillas). GET /cards."""
        return self._cached_get(
            "cards", {}, config.CACHE_TTL_WC_STATIC,
            f"wc_cards_{self.lang}",
        )
