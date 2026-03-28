"""
WinStake.ia — Cliente de The Odds API
Obtiene cuotas de mercado para La Liga desde The Odds API v4.
"""

import requests
import logging
from typing import Optional

import config
from src.cache import APICache

logger = logging.getLogger(__name__)


class OddsClient:
    """Cliente para The Odds API v4."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.ODDS_API_KEY
        self.base_url = config.ODDS_API_BASE
        self.cache = APICache()

        if not self.api_key or self.api_key == "tu_clave_aqui":
            logger.warning("⚠️  ODDS_API_KEY no configurada. Usando datos simulados.")
            self._mock_mode = True
        else:
            self._mock_mode = False

    def get_upcoming_odds(self) -> list[dict]:
        """
        Obtiene cuotas para los próximos partidos de La Liga.
        Retorna lista de partidos con cuotas promedio por resultado.
        """
        if self._mock_mode:
            return self._get_mock_odds()

        # Intentar caché primero
        cache_key = f"odds_{config.SPORT_KEY}"
        cached = self.cache.get(cache_key, config.CACHE_TTL_ODDS)
        if cached is not None:
            logger.info(f"✅ Cuotas desde caché ({len(cached)} partidos) — 0 requests usadas")
            return cached

        try:
            url = f"{self.base_url}/sports/{config.SPORT_KEY}/odds"
            params = {
                "apiKey": self.api_key,
                "regions": config.ODDS_REGIONS,
                "markets": config.ODDS_MARKETS,
                "oddsFormat": config.ODDS_FORMAT,
            }
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()

            raw_data = response.json()
            remaining = response.headers.get("x-requests-remaining", "?")
            logger.info(f"✅ Odds API: {len(raw_data)} partidos. Requests restantes: {remaining}")

            parsed = self._parse_odds(raw_data)

            # Guardar en caché
            self.cache.set(cache_key, parsed)
            logger.info(f"💾 Cuotas guardadas en caché (TTL: {config.CACHE_TTL_ODDS // 60}min)")

            return parsed

        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Odds API HTTP error: {e}")
            if e.response.status_code == 401:
                logger.error("   → API key inválida. Verifica ODDS_API_KEY en .env")
            elif e.response.status_code == 429:
                logger.error("   → Límite de requests alcanzado (500/mes en plan gratuito)")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Odds API connection error: {e}")
            return []

    def _parse_odds(self, raw_data: list[dict]) -> list[dict]:
        """Parsea respuesta de la API y calcula cuotas promedio por resultado."""
        matches = []

        for event in raw_data:
            match = {
                "id": event.get("id"),
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "commence_time": event.get("commence_time"),
                "odds_h2h": {"home": [], "draw": [], "away": []},
                "odds_totals": {"over_25": [], "under_25": []},
                "bookmakers_count": 0,
            }

            bookmakers = event.get("bookmakers", [])
            match["bookmakers_count"] = len(bookmakers)

            for bm in bookmakers:
                for market in bm.get("markets", []):
                    if market["key"] == "h2h":
                        outcomes = market.get("outcomes", [])
                        for o in outcomes:
                            if o["name"] == event["home_team"]:
                                match["odds_h2h"]["home"].append(o["price"])
                            elif o["name"] == event["away_team"]:
                                match["odds_h2h"]["away"].append(o["price"])
                            elif o["name"] == "Draw":
                                match["odds_h2h"]["draw"].append(o["price"])

                    elif market["key"] == "totals":
                        outcomes = market.get("outcomes", [])
                        for o in outcomes:
                            point = o.get("point", 2.5)
                            if point == 2.5:
                                if o["name"] == "Over":
                                    match["odds_totals"]["over_25"].append(o["price"])
                                elif o["name"] == "Under":
                                    match["odds_totals"]["under_25"].append(o["price"])

            # Calcular cuotas promedio (filtrando outliers)
            match["avg_odds"] = {
                "home": self._trimmed_mean(match["odds_h2h"]["home"]),
                "draw": self._trimmed_mean(match["odds_h2h"]["draw"]),
                "away": self._trimmed_mean(match["odds_h2h"]["away"]),
                "over_25": self._trimmed_mean(match["odds_totals"]["over_25"]),
                "under_25": self._trimmed_mean(match["odds_totals"]["under_25"]),
            }

            matches.append(match)

        return matches

    @staticmethod
    def _trimmed_mean(values: list[float]) -> Optional[float]:
        """Media recortada: elimina el valor más alto y más bajo si hay 4+ datos."""
        if not values:
            return None
        if len(values) < 4:
            return round(sum(values) / len(values), 2)

        sorted_vals = sorted(values)
        trimmed = sorted_vals[1:-1]  # Quita extremos
        return round(sum(trimmed) / len(trimmed), 2)

    def _get_mock_odds(self) -> list[dict]:
        """Datos simulados para desarrollo sin API key."""
        logger.info("🔧 Usando cuotas simuladas (modo desarrollo)")
        return [
            {
                "id": "mock_1", "home_team": "Rayo Vallecano", "away_team": "Elche",
                "commence_time": "2026-04-03T19:00:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 1.85, "draw": 3.40, "away": 4.20, "over_25": 2.10, "under_25": 1.75},
            },
            {
                "id": "mock_2", "home_team": "Real Sociedad", "away_team": "Levante",
                "commence_time": "2026-04-04T14:00:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 1.68, "draw": 3.60, "away": 5.00, "over_25": 1.95, "under_25": 1.85},
            },
            {
                "id": "mock_3", "home_team": "Mallorca", "away_team": "Real Madrid",
                "commence_time": "2026-04-04T16:15:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 5.50, "draw": 3.80, "away": 1.67, "over_25": 1.80, "under_25": 2.00},
            },
            {
                "id": "mock_4", "home_team": "Real Betis", "away_team": "Espanyol",
                "commence_time": "2026-04-04T18:30:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 1.75, "draw": 3.50, "away": 4.50, "over_25": 1.90, "under_25": 1.90},
            },
            {
                "id": "mock_5", "home_team": "Atlético Madrid", "away_team": "Barcelona",
                "commence_time": "2026-04-04T21:00:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 3.15, "draw": 3.30, "away": 2.10, "over_25": 1.85, "under_25": 1.95},
            },
            {
                "id": "mock_6", "home_team": "Getafe", "away_team": "Athletic Club",
                "commence_time": "2026-04-05T14:00:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 3.05, "draw": 3.10, "away": 2.90, "over_25": 2.30, "under_25": 1.60},
            },
            {
                "id": "mock_7", "home_team": "Valencia", "away_team": "Celta Vigo",
                "commence_time": "2026-04-05T16:15:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 2.38, "draw": 3.30, "away": 2.75, "over_25": 1.80, "under_25": 2.00},
            },
            {
                "id": "mock_8", "home_team": "Real Oviedo", "away_team": "Sevilla",
                "commence_time": "2026-04-05T18:30:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 2.75, "draw": 3.20, "away": 2.60, "over_25": 1.85, "under_25": 1.95},
            },
            {
                "id": "mock_9", "home_team": "Deportivo Alavés", "away_team": "Osasuna",
                "commence_time": "2026-04-05T21:00:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 2.42, "draw": 3.30, "away": 3.25, "over_25": 2.05, "under_25": 1.78},
            },
            {
                "id": "mock_10", "home_team": "Girona", "away_team": "Villarreal",
                "commence_time": "2026-04-06T21:00:00Z", "bookmakers_count": 5,
                "avg_odds": {"home": 2.87, "draw": 3.30, "away": 2.37, "over_25": 1.75, "under_25": 2.10},
            },
        ]
