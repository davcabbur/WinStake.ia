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

    def get_top_scorers(self, limit: int = 40) -> list[dict]:
        """Obtiene goleadores y asistentes de La Liga para estimar probabilidad de anotar."""
        if self._mock_mode:
            return self._get_mock_scorers()

        cache_key = f"top_scorers_{config.LA_LIGA_ID}_{config.CURRENT_SEASON}"
        cached = self.cache.get(cache_key, config.CACHE_TTL_H2H)
        if cached is not None:
            logger.info(f"✅ Goleadores desde caché ({len(cached)} jugadores)")
            return cached

        data = self._request("players/topscorers", {
            "league": config.LA_LIGA_ID,
            "season": config.CURRENT_SEASON,
        })
        if not data:
            return self._get_mock_scorers()

        try:
            result = []
            for p in data.get("response", [])[:limit]:
                player = p["player"]
                stats = p["statistics"][0]
                appearances = stats["games"]["appearences"] or 1
                goals = stats["goals"]["total"] or 0
                assists = stats["goals"]["assists"] or 0
                minutes = stats["games"]["minutes"] or 1
                team_name = stats["team"]["name"]
                team_id = stats["team"]["id"]

                goals_per_90 = (goals / minutes) * 90 if minutes > 0 else 0
                assists_per_90 = (assists / minutes) * 90 if minutes > 0 else 0

                result.append({
                    "player_name": player["name"],
                    "player_id": player["id"],
                    "team_name": team_name,
                    "team_id": team_id,
                    "goals": goals,
                    "assists": assists,
                    "appearances": appearances,
                    "minutes": minutes,
                    "goals_per_90": round(goals_per_90, 3),
                    "assists_per_90": round(assists_per_90, 3),
                })

            self.cache.set(cache_key, result)
            logger.info(f"💾 Goleadores guardados en caché ({len(result)} jugadores)")
            return result

        except (KeyError, TypeError, IndexError) as e:
            logger.error(f"❌ Error parseando top scorers: {e}")
            return self._get_mock_scorers()

    def _get_mock_scorers(self) -> list[dict]:
        """Goleadores simulados basados en datos reales J30 2025-26."""
        logger.info("🔧 Usando goleadores simulados")
        players = [
            ("Robert Lewandowski", 1001, "Barcelona", 1001, 25, 5, 28, 2340),
            ("Kylian Mbappé", 1002, "Real Madrid", 1002, 20, 6, 29, 2520),
            ("Raphinha", 1003, "Barcelona", 1001, 16, 10, 28, 2380),
            ("Alexander Sörloth", 1004, "Atlético Madrid", 1004, 14, 3, 27, 2160),
            ("Ayoze Pérez", 1005, "Villarreal", 1003, 13, 5, 28, 2300),
            ("Antoine Griezmann", 1006, "Atlético Madrid", 1004, 11, 8, 28, 2200),
            ("Iago Aspas", 1007, "Celta Vigo", 1006, 11, 5, 27, 2100),
            ("Vinicius Jr", 1008, "Real Madrid", 1002, 10, 7, 25, 2050),
            ("Iker Muniain", 1009, "Real Betis", 1005, 9, 4, 26, 2000),
            ("Gorka Guruzeta", 1010, "Athletic Club", 1009, 9, 3, 27, 2150),
            ("Ante Budimir", 1011, "Osasuna", 1010, 9, 2, 28, 2250),
            ("Borja Iglesias", 1012, "Real Betis", 1005, 8, 4, 24, 1800),
            ("Dani Olmo", 1013, "Barcelona", 1001, 8, 6, 22, 1700),
            ("Samu Omorodion", 1014, "Atlético Madrid", 1004, 8, 2, 25, 1900),
            ("Hugo Duro", 1015, "Valencia", 1012, 8, 3, 28, 2200),
            ("Bryan Gil", 1016, "Girona", 1013, 7, 4, 26, 1950),
            ("Chimy Ávila", 1017, "Osasuna", 1010, 7, 3, 24, 1800),
            ("Óscar Trejo", 1018, "Rayo Vallecano", 1014, 6, 6, 27, 2100),
            ("Javier Puado", 1019, "Espanyol", 1011, 7, 3, 28, 2300),
            ("Álvaro García", 1020, "Rayo Vallecano", 1014, 6, 3, 26, 2000),
        ]
        return [
            {
                "player_name": name, "player_id": pid,
                "team_name": team, "team_id": tid,
                "goals": g, "assists": a, "appearances": apps, "minutes": mins,
                "goals_per_90": round((g / mins) * 90, 3) if mins > 0 else 0,
                "assists_per_90": round((a / mins) * 90, 3) if mins > 0 else 0,
            }
            for name, pid, team, tid, g, a, apps, mins in players
        ]

    def get_players_for_match(self, home_team: str, away_team: str, scorers: list[dict]) -> dict:
        """Filtra goleadores relevantes para un partido específico."""
        home_players = []
        away_players = []

        home_lower = home_team.lower()
        away_lower = away_team.lower()

        for p in scorers:
            team_lower = p["team_name"].lower()
            if home_lower in team_lower or team_lower in home_lower:
                home_players.append(p)
            elif away_lower in team_lower or team_lower in away_lower:
                away_players.append(p)

        # Ordenar por goles/90 desc y tomar top 3 de cada equipo
        home_players.sort(key=lambda x: x["goals_per_90"], reverse=True)
        away_players.sort(key=lambda x: x["goals_per_90"], reverse=True)

        return {
            "home": home_players[:3],
            "away": away_players[:3],
        }

    def get_today_fixtures(self) -> list[dict]:
        """
        Obtiene los fixtures de La Liga programados para hoy.
        Usado para mapear partidos a fixture_id y luego pedir onces.
        """
        if self._mock_mode:
            return []

        from datetime import date
        today = date.today().isoformat()

        cache_key = f"today_fixtures_{today}"
        cached = self.cache.get(cache_key, 60 * 60)  # 1 hora — fixtures del día no cambian
        if cached is not None:
            return cached

        data = self._request("fixtures", {
            "league": config.LA_LIGA_ID,
            "season": config.CURRENT_SEASON,
            "date": today,
        })
        if not data:
            return []

        try:
            result = [
                {
                    "fixture_id": f["fixture"]["id"],
                    "home_team": f["teams"]["home"]["name"],
                    "away_team": f["teams"]["away"]["name"],
                    "status": f["fixture"]["status"]["short"],  # NS, 1H, HT, 2H, FT…
                    "date": f["fixture"]["date"],
                }
                for f in data.get("response", [])
            ]
            self.cache.set(cache_key, result)
            logger.info(f"📅 {len(result)} fixture(s) de La Liga hoy")
            return result
        except (KeyError, TypeError) as e:
            logger.error(f"❌ Error parseando fixtures de hoy: {e}")
            return []

    def get_fixture_lineups(self, fixture_id: int) -> Optional[dict]:
        """
        Obtiene las alineaciones oficiales de un fixture.
        Retorna None si todavía no están publicadas (pre-partido).
        La respuesta incluye startXI, suplentes, formación y entrenador.
        """
        if self._mock_mode:
            return None

        # Cache corto (5 min) — los onces pueden llegar en cualquier momento
        cache_key = f"lineups_{fixture_id}"
        cached = self.cache.get(cache_key, 5 * 60)
        if cached is not None:
            return cached

        data = self._request("fixtures/lineups", {"fixture": fixture_id})
        if not data:
            return None

        response = data.get("response", [])
        if len(response) < 2:
            return None  # Onces aún no publicados

        try:
            def _parse_side(side_data: dict) -> dict:
                return {
                    "team": side_data["team"]["name"],
                    "formation": side_data.get("formation", ""),
                    "coach": side_data.get("coach", {}).get("name", ""),
                    "startXI": [
                        {
                            "name": p["player"]["name"],
                            "number": p["player"].get("number"),
                            "pos": p["player"].get("pos", ""),
                        }
                        for p in side_data.get("startXI", [])
                    ],
                    "substitutes": [
                        p["player"]["name"]
                        for p in side_data.get("substitutes", [])
                    ],
                }

            result = {
                "home": _parse_side(response[0]),
                "away": _parse_side(response[1]),
            }

            # Solo cachear si el once está completo (11 jugadores)
            if len(result["home"]["startXI"]) >= 11 and len(result["away"]["startXI"]) >= 11:
                self.cache.set(cache_key, result)
                logger.info(f"📋 Onces confirmados para fixture {fixture_id}")

            return result
        except (KeyError, TypeError, IndexError) as e:
            logger.error(f"❌ Error parseando lineups fixture {fixture_id}: {e}")
            return None

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
