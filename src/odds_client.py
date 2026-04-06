"""
WinStake.ia — Cliente de The Odds API
Obtiene cuotas de mercado para La Liga desde The Odds API v4.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import config
from src.cache import APICache

logger = logging.getLogger(__name__)


def _create_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Crea una sesión HTTP con retry y backoff exponencial."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,  # 0.5s, 1s, 2s
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class OddsClient:
    """Cliente para The Odds API v4."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.ODDS_API_KEY
        self.base_url = config.ODDS_API_BASE
        self.cache = APICache()
        self.session = _create_session()

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
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            raw_data = response.json()
            remaining = response.headers.get("x-requests-remaining", "?")
            logger.info(f"✅ Odds API: {len(raw_data)} partidos. Requests restantes: {remaining}")

            parsed = self._parse_odds(raw_data)

            # Filtrar solo partidos de la próxima jornada (7 días)
            parsed = self._filter_next_matchday(parsed)
            logger.info(f"📅 Tras filtro de jornada: {len(parsed)} partidos")

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

    @staticmethod
    def _filter_next_matchday(matches: list[dict], window_days: int = 7) -> list[dict]:
        """
        Filtra partidos para mostrar solo la próxima jornada.

        Estrategia: toma el primer partido (más cercano) y agrupa todos los
        que caen dentro de 4 días desde ese primero. Una jornada de La Liga
        se juega entre viernes y lunes (4 días máximo).
        """
        if not matches:
            return matches

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=window_days)

        # 1. Filtrar partidos futuros dentro de la ventana
        future = []
        for m in matches:
            ct = m.get("commence_time", "")
            if not ct:
                continue
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                if now - timedelta(hours=2) <= dt <= cutoff:
                    m["_dt"] = dt
                    future.append(m)
            except (ValueError, TypeError):
                continue

        if not future:
            return matches  # Fallback: devolver todo

        # 2. Ordenar por fecha
        future.sort(key=lambda m: m["_dt"])

        # 3. Agrupar jornada: desde el primer partido, tomar todos dentro de 4 días
        first_dt = future[0]["_dt"]
        matchday_end = first_dt + timedelta(days=4)

        result = []
        for m in future:
            if m["_dt"] <= matchday_end:
                m.pop("_dt", None)
                result.append(m)

        return result

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
                "odds_totals": {"over_15": [], "under_15": [], "over_25": [], "under_25": [], "over_35": [], "under_35": []},
                "odds_btts": {"yes": [], "no": []},
                "odds_double_chance": {"1x": [], "x2": [], "12": []},
                "bookmakers_count": 0,
            }

            bookmakers = event.get("bookmakers", [])
            match["bookmakers_count"] = len(bookmakers)

            for bm in bookmakers:
                for market in bm.get("markets", []):
                    if market["key"] == "h2h":
                        for o in market.get("outcomes", []):
                            if o["name"] == event["home_team"]:
                                match["odds_h2h"]["home"].append(o["price"])
                            elif o["name"] == event["away_team"]:
                                match["odds_h2h"]["away"].append(o["price"])
                            elif o["name"] == "Draw":
                                match["odds_h2h"]["draw"].append(o["price"])

                    elif market["key"] == "totals":
                        for o in market.get("outcomes", []):
                            point = o.get("point", 2.5)
                            if o["name"] == "Over":
                                if point == 1.5:
                                    match["odds_totals"]["over_15"].append(o["price"])
                                elif point == 2.5:
                                    match["odds_totals"]["over_25"].append(o["price"])
                                elif point == 3.5:
                                    match["odds_totals"]["over_35"].append(o["price"])
                            elif o["name"] == "Under":
                                if point == 1.5:
                                    match["odds_totals"]["under_15"].append(o["price"])
                                elif point == 2.5:
                                    match["odds_totals"]["under_25"].append(o["price"])
                                elif point == 3.5:
                                    match["odds_totals"]["under_35"].append(o["price"])

                    elif market["key"] == "btts":
                        for o in market.get("outcomes", []):
                            if o["name"] == "Yes":
                                match["odds_btts"]["yes"].append(o["price"])
                            elif o["name"] == "No":
                                match["odds_btts"]["no"].append(o["price"])

                    elif market["key"] == "double_chance":
                        for o in market.get("outcomes", []):
                            name = o["name"]
                            if name == f"{event['home_team']} or Draw":
                                match["odds_double_chance"]["1x"].append(o["price"])
                            elif name == f"{event['away_team']} or Draw":
                                match["odds_double_chance"]["x2"].append(o["price"])
                            elif "Draw" not in name:
                                match["odds_double_chance"]["12"].append(o["price"])

            # Calcular cuotas promedio (filtrando outliers)
            match["avg_odds"] = {
                "home": self._trimmed_mean(match["odds_h2h"]["home"]),
                "draw": self._trimmed_mean(match["odds_h2h"]["draw"]),
                "away": self._trimmed_mean(match["odds_h2h"]["away"]),
                "double_chance_1x": self._trimmed_mean(match["odds_double_chance"]["1x"]),
                "double_chance_x2": self._trimmed_mean(match["odds_double_chance"]["x2"]),
                "double_chance_12": self._trimmed_mean(match["odds_double_chance"]["12"]),
                "over_15": self._trimmed_mean(match["odds_totals"]["over_15"]),
                "under_15": self._trimmed_mean(match["odds_totals"]["under_15"]),
                "over_25": self._trimmed_mean(match["odds_totals"]["over_25"]),
                "under_25": self._trimmed_mean(match["odds_totals"]["under_25"]),
                "over_35": self._trimmed_mean(match["odds_totals"]["over_35"]),
                "under_35": self._trimmed_mean(match["odds_totals"]["under_35"]),
                "btts_yes": self._trimmed_mean(match["odds_btts"]["yes"]),
                "btts_no": self._trimmed_mean(match["odds_btts"]["no"]),
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
        """Datos simulados para desarrollo sin API key — Jornada 31."""
        logger.info("🔧 Usando cuotas simuladas (modo desarrollo) — J31")

        def _full_odds(home, draw, away, o25, u25, btts_y=None, btts_n=None):
            """Genera dict de odds completo con mercados derivados."""
            btts_y = btts_y or round(1 / (0.55 if o25 < 2.0 else 0.45), 2)
            btts_n = btts_n or round(1 / (1 - 1/btts_y), 2)
            dc_1x = round(1 / (1/home + 1/draw) * 0.92, 2)
            dc_x2 = round(1 / (1/away + 1/draw) * 0.92, 2)
            dc_12 = round(1 / (1/home + 1/away) * 0.92, 2)
            o15 = round(max(1.05, o25 * 0.62), 2)
            u15 = round(1 / (1 - 1/o15), 2)
            o35 = round(o25 * 1.65, 2)
            u35 = round(1 / (1 - 1/o35), 2)
            return {
                "home": home, "draw": draw, "away": away,
                "double_chance_1x": dc_1x, "double_chance_x2": dc_x2, "double_chance_12": dc_12,
                "over_15": o15, "under_15": u15,
                "over_25": o25, "under_25": u25,
                "over_35": o35, "under_35": u35,
                "btts_yes": btts_y, "btts_no": btts_n,
            }

        return [
            {"id": "mock_1", "home_team": "Rayo Vallecano", "away_team": "Elche",
             "commence_time": "2026-04-10T19:00:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(1.85, 3.40, 4.20, 2.10, 1.75)},
            {"id": "mock_2", "home_team": "Real Sociedad", "away_team": "Levante",
             "commence_time": "2026-04-11T14:00:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(1.68, 3.60, 5.00, 1.95, 1.85)},
            {"id": "mock_3", "home_team": "Mallorca", "away_team": "Real Madrid",
             "commence_time": "2026-04-11T16:15:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(5.50, 3.80, 1.67, 1.80, 2.00)},
            {"id": "mock_4", "home_team": "Real Betis", "away_team": "Espanyol",
             "commence_time": "2026-04-11T18:30:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(1.75, 3.50, 4.50, 1.90, 1.90)},
            {"id": "mock_5", "home_team": "Atlético Madrid", "away_team": "Barcelona",
             "commence_time": "2026-04-11T21:00:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(3.15, 3.30, 2.10, 1.85, 1.95)},
            {"id": "mock_6", "home_team": "Getafe", "away_team": "Athletic Club",
             "commence_time": "2026-04-12T14:00:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(3.05, 3.10, 2.90, 2.30, 1.60)},
            {"id": "mock_7", "home_team": "Valencia", "away_team": "Celta Vigo",
             "commence_time": "2026-04-12T16:15:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(2.38, 3.30, 2.75, 1.80, 2.00)},
            {"id": "mock_8", "home_team": "Real Oviedo", "away_team": "Sevilla",
             "commence_time": "2026-04-12T18:30:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(2.75, 3.20, 2.60, 1.85, 1.95)},
            {"id": "mock_9", "home_team": "Deportivo Alavés", "away_team": "Osasuna",
             "commence_time": "2026-04-12T21:00:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(2.42, 3.30, 3.25, 2.05, 1.78)},
            {"id": "mock_10", "home_team": "Girona", "away_team": "Villarreal",
             "commence_time": "2026-04-13T21:00:00Z", "bookmakers_count": 5,
             "avg_odds": _full_odds(2.87, 3.30, 2.37, 1.75, 2.10)},
        ]
