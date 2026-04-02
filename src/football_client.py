"""
WinStake.ia — Cliente de API-Football
Obtiene estadísticas, clasificación y fixtures de La Liga.
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


class FootballClient:
    """Cliente para API-Football (api-sports.io)."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.FOOTBALL_API_KEY
        self.base_url = config.FOOTBALL_API_BASE
        self.headers = {
            "x-apisports-key": self.api_key,
        }
        self.cache = APICache()
        self.session = _create_session()

        if not self.api_key or self.api_key == "tu_clave_aqui":
            logger.warning("⚠️  FOOTBALL_API_KEY no configurada. Usando datos simulados.")
            self._mock_mode = True
        else:
            self._mock_mode = False

    def _request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Realiza una petición a la API."""
        try:
            url = f"{self.base_url}/{endpoint}"
            response = self.session.get(url, headers=self.headers, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            if data.get("errors"):
                logger.error(f"❌ API-Football error: {data['errors']}")
                return None

            remaining = data.get("paging", {}).get("current", "?")
            logger.debug(f"✅ API-Football /{endpoint}: {remaining} resultados")
            return data
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ API-Football HTTP error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ API-Football connection error: {e}")
            return None

    def get_standings(self) -> list[dict]:
        """Obtiene la clasificación actual de La Liga."""
        if self._mock_mode:
            return self._get_mock_standings()

        # Intentar caché primero
        cache_key = f"standings_{config.LA_LIGA_ID}_{config.CURRENT_SEASON}"
        cached = self.cache.get(cache_key, config.CACHE_TTL_STANDINGS)
        if cached is not None:
            logger.info(f"✅ Clasificación desde caché ({len(cached)} equipos) — 0 requests usadas")
            return cached

        data = self._request("standings", {
            "league": config.LA_LIGA_ID,
            "season": config.CURRENT_SEASON,
        })
        if not data:
            return self._get_mock_standings()

        try:
            standings_raw = data["response"][0]["league"]["standings"][0]
            result = [
                {
                    "team_id": team["team"]["id"],
                    "team_name": team["team"]["name"],
                    "rank": team["rank"],
                    "points": team["points"],
                    "played": team["all"]["played"],
                    "wins": team["all"]["win"],
                    "draws": team["all"]["draw"],
                    "losses": team["all"]["lose"],
                    "goals_for": team["all"]["goals"]["for"],
                    "goals_against": team["all"]["goals"]["against"],
                    "goal_diff": team["goalsDiff"],
                    "form": team.get("form", ""),
                    "home": {
                        "played": team["home"]["played"],
                        "wins": team["home"]["win"],
                        "draws": team["home"]["draw"],
                        "losses": team["home"]["lose"],
                        "goals_for": team["home"]["goals"]["for"],
                        "goals_against": team["home"]["goals"]["against"],
                    },
                    "away": {
                        "played": team["away"]["played"],
                        "wins": team["away"]["win"],
                        "draws": team["away"]["draw"],
                        "losses": team["away"]["lose"],
                        "goals_for": team["away"]["goals"]["for"],
                        "goals_against": team["away"]["goals"]["against"],
                    },
                }
                for team in standings_raw
            ]

            self.cache.set(cache_key, result)
            logger.info(f"💾 Clasificación guardada en caché (TTL: {config.CACHE_TTL_STANDINGS // 3600}h)")
            return result

        except (KeyError, IndexError) as e:
            logger.error(f"❌ Error parseando standings: {e}")
            return self._get_mock_standings()

    def get_team_stats(self, team_id: int) -> Optional[dict]:
        """Obtiene estadísticas detalladas de un equipo."""
        if self._mock_mode:
            return None

        # Intentar caché
        cache_key = f"team_stats_{team_id}_{config.CURRENT_SEASON}"
        cached = self.cache.get(cache_key, config.CACHE_TTL_TEAM_STATS)
        if cached is not None:
            return cached

        data = self._request("teams/statistics", {
            "league": config.LA_LIGA_ID,
            "season": config.CURRENT_SEASON,
            "team": team_id,
        })
        if not data:
            return None

        try:
            stats = data["response"]
            result = {
                "team_id": stats["team"]["id"],
                "team_name": stats["team"]["name"],
                "form": stats.get("form", ""),
                "goals_for_avg": stats["goals"]["for"]["average"]["total"],
                "goals_against_avg": stats["goals"]["against"]["average"]["total"],
                "goals_for_home_avg": stats["goals"]["for"]["average"]["home"],
                "goals_against_home_avg": stats["goals"]["against"]["average"]["home"],
                "goals_for_away_avg": stats["goals"]["for"]["average"]["away"],
                "goals_against_away_avg": stats["goals"]["against"]["average"]["away"],
                "clean_sheets_total": stats["clean_sheet"]["total"],
                "failed_to_score_total": stats["failed_to_score"]["total"],
            }

            self.cache.set(cache_key, result)
            return result

        except (KeyError, TypeError) as e:
            logger.error(f"❌ Error parseando team stats: {e}")
            return None

    def get_h2h(self, team1_id: int, team2_id: int, last: int = 5) -> list[dict]:
        """Obtiene historial directo entre dos equipos."""
        if self._mock_mode:
            return []

        # Intentar caché
        cache_key = f"h2h_{min(team1_id, team2_id)}_{max(team1_id, team2_id)}"
        cached = self.cache.get(cache_key, config.CACHE_TTL_H2H)
        if cached is not None:
            return cached

        data = self._request("fixtures/headtohead", {
            "h2h": f"{team1_id}-{team2_id}",
            "last": last,
        })
        if not data:
            return []

        try:
            result = [
                {
                    "date": fix["fixture"]["date"],
                    "home_team": fix["teams"]["home"]["name"],
                    "away_team": fix["teams"]["away"]["name"],
                    "home_goals": fix["goals"]["home"],
                    "away_goals": fix["goals"]["away"],
                    "home_winner": fix["teams"]["home"]["winner"],
                }
                for fix in data.get("response", [])
            ]

            self.cache.set(cache_key, result)
            return result

        except (KeyError, TypeError):
            return []

    def find_team_in_standings(self, team_name: str, standings: list[dict]) -> Optional[dict]:
        """Busca un equipo en la clasificación por nombre (fuzzy match)."""
        name_lower = team_name.lower()

        # Mapeo de nombres comunes The Odds API → API-Football
        name_map = {
            "atletico madrid": ["atletico madrid", "atlético madrid", "atl. madrid", "club atletico de madrid"],
            "athletic club": ["athletic club", "athletic bilbao"],
            "real sociedad": ["real sociedad"],
            "real betis": ["real betis", "betis"],
            "celta vigo": ["celta vigo", "celta de vigo", "rc celta"],
            "deportivo alavés": ["deportivo alaves", "alavés", "alaves", "deportivo alavés"],
            "rayo vallecano": ["rayo vallecano"],
            "real oviedo": ["real oviedo", "oviedo"],
        }

        for team in standings:
            team_lower = team["team_name"].lower()

            # Coincidencia directa
            if name_lower in team_lower or team_lower in name_lower:
                return team

            # Buscar en mapeo
            for canonical, aliases in name_map.items():
                if any(a in name_lower for a in aliases) or any(a in team_lower for a in aliases):
                    if any(a in name_lower for a in aliases) and any(a in team_lower for a in aliases):
                        return team

        logger.warning(f"⚠️  Equipo no encontrado en standings: {team_name}")
        return None

    def _get_mock_standings(self) -> list[dict]:
        """Datos simulados basados en la clasificación real J29."""
        logger.info("🔧 Usando clasificación simulada (modo desarrollo)")
        #                Name              pts  pld  w  d  l  gf gc  xgf   xga
        teams = [
            ("Barcelona",          77, 29, 24, 5, 0, 78, 28, 72.5, 31.2),
            ("Real Madrid",        69, 29, 22, 3, 4, 63, 26, 58.0, 28.5),
            ("Villarreal",         58, 29, 18, 4, 7, 54, 34, 50.8, 36.1),
            ("Atlético Madrid",    57, 29, 17, 6, 6, 49, 28, 44.3, 30.4),
            ("Real Betis",         44, 29, 11, 11, 7, 44, 37, 40.2, 38.9),
            ("Celta Vigo",         41, 29, 10, 11, 8, 41, 35, 38.5, 36.7),
            ("Real Sociedad",      38, 29, 10, 8, 11, 44, 45, 39.1, 41.3),
            ("Getafe",             38, 29, 11, 5, 13, 25, 31, 22.8, 33.5),
            ("Athletic Club",      38, 29, 11, 5, 13, 32, 41, 30.5, 38.2),
            ("Osasuna",            37, 29, 10, 7, 12, 34, 35, 31.9, 36.8),
            ("Espanyol",           37, 29, 10, 7, 12, 36, 44, 33.4, 42.1),
            ("Valencia",           35, 29, 9, 8, 12, 32, 42, 30.1, 39.7),
            ("Girona",             34, 29, 8, 10, 11, 31, 44, 35.2, 40.5),
            ("Rayo Vallecano",     32, 29, 7, 11, 11, 28, 35, 26.3, 37.1),
            ("Sevilla",            31, 29, 8, 7, 14, 37, 49, 34.8, 45.6),
            ("Deportivo Alavés",   31, 29, 8, 7, 14, 30, 41, 28.1, 43.2),
            ("Elche",              29, 29, 6, 11, 12, 38, 46, 34.5, 44.8),
            ("Mallorca",           28, 29, 7, 7, 15, 34, 47, 29.7, 44.1),
            ("Levante",            26, 29, 6, 8, 15, 34, 48, 31.2, 46.3),
            ("Real Oviedo",        21, 29, 4, 9, 16, 20, 48, 19.5, 45.9),
        ]

        standings = []
        for i, (name, pts, played, w, d, l, gf, gc, xgf, xga) in enumerate(teams, 1):
            # Estimar splits local/visitante (aprox 60/40)
            home_p = played // 2 + (1 if i % 2 == 0 else 0)
            away_p = played - home_p
            home_gf = int(gf * 0.6)
            away_gf = gf - home_gf
            home_gc = int(gc * 0.4)
            away_gc = gc - home_gc

            standings.append({
                "team_id": 1000 + i,
                "team_name": name,
                "rank": i,
                "points": pts,
                "played": played,
                "wins": w,
                "draws": d,
                "losses": l,
                "goals_for": gf,
                "goals_against": gc,
                "goal_diff": gf - gc,
                "form": "",
                "xg_for": xgf,
                "xg_against": xga,
                "xg_for_per_match": round(xgf / played, 2),
                "xg_against_per_match": round(xga / played, 2),
                "home": {
                    "played": home_p,
                    "wins": int(w * 0.6),
                    "draws": d // 2,
                    "losses": home_p - int(w * 0.6) - d // 2,
                    "goals_for": home_gf,
                    "goals_against": home_gc,
                },
                "away": {
                    "played": away_p,
                    "wins": w - int(w * 0.6),
                    "draws": d - d // 2,
                    "losses": away_p - (w - int(w * 0.6)) - (d - d // 2),
                    "goals_for": away_gf,
                    "goals_against": away_gc,
                },
            })

        return standings
