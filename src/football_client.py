"""
WinStake.ia — Cliente de API-Football
Obtiene estadísticas, clasificación y fixtures de La Liga.
"""

import requests
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)


class FootballClient:
    """Cliente para API-Football (api-sports.io)."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.FOOTBALL_API_KEY
        self.base_url = config.FOOTBALL_API_BASE
        self.headers = {
            "x-apisports-key": self.api_key,
        }

        if not self.api_key or self.api_key == "tu_clave_aqui":
            logger.warning("⚠️  FOOTBALL_API_KEY no configurada. Usando datos simulados.")
            self._mock_mode = True
        else:
            self._mock_mode = False

    def _request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Realiza una petición a la API."""
        try:
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(url, headers=self.headers, params=params, timeout=15)
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

        data = self._request("standings", {
            "league": config.LA_LIGA_ID,
            "season": config.CURRENT_SEASON,
        })
        if not data:
            return self._get_mock_standings()

        try:
            standings_raw = data["response"][0]["league"]["standings"][0]
            return [
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
        except (KeyError, IndexError) as e:
            logger.error(f"❌ Error parseando standings: {e}")
            return self._get_mock_standings()

    def get_team_stats(self, team_id: int) -> Optional[dict]:
        """Obtiene estadísticas detalladas de un equipo."""
        if self._mock_mode:
            return None

        data = self._request("teams/statistics", {
            "league": config.LA_LIGA_ID,
            "season": config.CURRENT_SEASON,
            "team": team_id,
        })
        if not data:
            return None

        try:
            stats = data["response"]
            return {
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
        except (KeyError, TypeError) as e:
            logger.error(f"❌ Error parseando team stats: {e}")
            return None

    def get_h2h(self, team1_id: int, team2_id: int, last: int = 5) -> list[dict]:
        """Obtiene historial directo entre dos equipos."""
        if self._mock_mode:
            return []

        data = self._request("fixtures/headtohead", {
            "h2h": f"{team1_id}-{team2_id}",
            "last": last,
        })
        if not data:
            return []

        try:
            return [
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
        teams = [
            ("Barcelona", 77, 29, 24, 5, 0, 78, 28),
            ("Real Madrid", 69, 29, 22, 3, 4, 63, 26),
            ("Villarreal", 58, 29, 18, 4, 7, 54, 34),
            ("Atlético Madrid", 57, 29, 17, 6, 6, 49, 28),
            ("Real Betis", 44, 29, 11, 11, 7, 44, 37),
            ("Celta Vigo", 41, 29, 10, 11, 8, 41, 35),
            ("Real Sociedad", 38, 29, 10, 8, 11, 44, 45),
            ("Getafe", 38, 29, 11, 5, 13, 25, 31),
            ("Athletic Club", 38, 29, 11, 5, 13, 32, 41),
            ("Osasuna", 37, 29, 10, 7, 12, 34, 35),
            ("Espanyol", 37, 29, 10, 7, 12, 36, 44),
            ("Valencia", 35, 29, 9, 8, 12, 32, 42),
            ("Girona", 34, 29, 8, 10, 11, 31, 44),
            ("Rayo Vallecano", 32, 29, 7, 11, 11, 28, 35),
            ("Sevilla", 31, 29, 8, 7, 14, 37, 49),
            ("Deportivo Alavés", 31, 29, 8, 7, 14, 30, 41),
            ("Elche", 29, 29, 6, 11, 12, 38, 46),
            ("Mallorca", 28, 29, 7, 7, 15, 34, 47),
            ("Levante", 26, 29, 6, 8, 15, 34, 48),
            ("Real Oviedo", 21, 29, 4, 9, 16, 20, 48),
        ]

        standings = []
        for i, (name, pts, played, w, d, l, gf, gc) in enumerate(teams, 1):
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
