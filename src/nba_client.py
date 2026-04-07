"""
WinStake.ia — Cliente de estadísticas NBA
Obtiene standings y stats de equipos usando nba_api (stats.nba.com).
No requiere API key.
"""

import logging
import time
from typing import Optional

from src.cache import APICache
import config

logger = logging.getLogger(__name__)

NBA_SEASON = "2025-26"


class NBAClient:
    """Cliente para estadísticas NBA via nba_api."""

    def __init__(self, api_key: str = None):
        self.cache = APICache()
        self._mock_mode = False

    def get_standings(self) -> list[dict]:
        """Obtiene la clasificación actual de la NBA."""
        if self._mock_mode:
            return self._get_mock_standings()

        cache_key = f"nba_standings_{NBA_SEASON}"
        cached = self.cache.get(cache_key, config.CACHE_TTL_STANDINGS)
        if cached is not None:
            logger.info(f"Clasificación NBA desde caché ({len(cached)} equipos)")
            return cached

        try:
            from nba_api.stats.endpoints import leaguestandings
            time.sleep(0.6)  # Rate limit: stats.nba.com
            raw = leaguestandings.LeagueStandings(season=NBA_SEASON)
            df = raw.get_data_frames()[0]

            result = []
            for _, row in df.iterrows():
                played = int(row["WINS"]) + int(row["LOSSES"])
                ppg = float(row["PointsPG"]) if row["PointsPG"] else 0
                opp_ppg = float(row["OppPointsPG"]) if row["OppPointsPG"] else 0

                result.append({
                    "team_id": int(row["TeamID"]),
                    "team_name": f"{row['TeamCity']} {row['TeamName']}",
                    "rank": int(row["PlayoffRank"]) if row["PlayoffRank"] else 0,
                    "played": played,
                    "wins": int(row["WINS"]),
                    "losses": int(row["LOSSES"]),
                    "points_for": round(ppg * played),
                    "points_against": round(opp_ppg * played),
                    "point_diff": round(float(row["DiffPointsPG"]) * played) if row["DiffPointsPG"] else 0,
                    "win_pct": float(row["WinPCT"]) if row["WinPCT"] else 0,
                    "streak": 0,
                    "form": str(row.get("L10", "")),
                    "conference": str(row["Conference"]),
                    "pace": 100.0,  # nba_api no tiene pace en standings
                    "std_dev_factor": 1.0,
                    "ppg": ppg,
                    "opp_ppg": opp_ppg,
                })

            logger.info(f"Standings NBA: {len(result)} equipos (nba_api)")
            self.cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.error(f"Error obteniendo standings NBA: {e}")
            logger.info("Usando standings simulados como fallback")
            return self._get_mock_standings()

    def get_h2h(self, team1_id: int, team2_id: int, last: int = 5) -> list[dict]:
        """Obtiene H2H entre dos equipos NBA (temporada actual)."""
        if self._mock_mode:
            return []

        cache_key = f"nba_h2h_{min(team1_id, team2_id)}_{max(team1_id, team2_id)}"
        cached = self.cache.get(cache_key, config.CACHE_TTL_H2H)
        if cached is not None:
            return cached

        try:
            from nba_api.stats.endpoints import teamgamelog
            from nba_api.stats.static import teams as nba_teams
            time.sleep(0.6)
            log = teamgamelog.TeamGameLog(team_id=team1_id, season=NBA_SEASON)
            df = log.get_data_frames()[0]

            # Buscar abbreviation del team2
            all_teams = nba_teams.get_teams()
            team2_info = next((t for t in all_teams if t["id"] == team2_id), None)
            if not team2_info:
                return []
            team2_abbrev = team2_info["abbreviation"]

            h2h_games = df[df["MATCHUP"].str.contains(team2_abbrev, na=False)].head(last)

            result = []
            for _, game in h2h_games.iterrows():
                is_home = "vs." in game["MATCHUP"]
                pts = int(game["PTS"])
                wl = game["WL"]
                # Estimar puntos del rival desde +/-
                plus_minus = int(game["PLUS_MINUS"]) if game["PLUS_MINUS"] else 0
                opp_pts = pts - plus_minus

                if is_home:
                    result.append({
                        "date": game["GAME_DATE"],
                        "home_team": game["MATCHUP"].split(" vs.")[0].strip(),
                        "away_team": team2_abbrev,
                        "home_goals": pts,
                        "away_goals": opp_pts,
                        "home_winner": wl == "W",
                    })
                else:
                    result.append({
                        "date": game["GAME_DATE"],
                        "home_team": team2_abbrev,
                        "away_team": game["MATCHUP"].split(" @ ")[0].strip(),
                        "home_goals": opp_pts,
                        "away_goals": pts,
                        "home_winner": wl == "L",
                    })

            self.cache.set(cache_key, result)
            return result

        except Exception as e:
            logger.warning(f"Error obteniendo H2H NBA: {e}")
            return []

    def find_team_in_standings(self, team_name: str, standings: list[dict]) -> Optional[dict]:
        """Busca un equipo NBA en los standings por nombre (fuzzy match)."""
        name_lower = team_name.lower()

        # Mapeo The Odds API -> nba_api
        name_map = {
            "los angeles lakers": ["lakers", "la lakers"],
            "los angeles clippers": ["clippers", "la clippers"],
            "golden state warriors": ["warriors", "golden state"],
            "oklahoma city thunder": ["thunder", "okc"],
            "san antonio spurs": ["spurs", "san antonio"],
            "new york knicks": ["knicks", "new york"],
            "brooklyn nets": ["nets", "brooklyn"],
            "portland trail blazers": ["trail blazers", "blazers", "portland"],
            "minnesota timberwolves": ["timberwolves", "wolves", "minnesota"],
            "new orleans pelicans": ["pelicans", "new orleans"],
            "sacramento kings": ["kings", "sacramento"],
            "indiana pacers": ["pacers", "indiana"],
            "philadelphia 76ers": ["76ers", "sixers", "philadelphia"],
            "cleveland cavaliers": ["cavaliers", "cavs", "cleveland"],
            "milwaukee bucks": ["bucks", "milwaukee"],
            "boston celtics": ["celtics", "boston"],
            "phoenix suns": ["suns", "phoenix"],
            "denver nuggets": ["nuggets", "denver"],
            "memphis grizzlies": ["grizzlies", "memphis"],
            "dallas mavericks": ["mavericks", "mavs", "dallas"],
            "houston rockets": ["rockets", "houston"],
            "miami heat": ["heat", "miami"],
            "chicago bulls": ["bulls", "chicago"],
            "toronto raptors": ["raptors", "toronto"],
            "atlanta hawks": ["hawks", "atlanta"],
            "orlando magic": ["magic", "orlando"],
            "detroit pistons": ["pistons", "detroit"],
            "charlotte hornets": ["hornets", "charlotte"],
            "utah jazz": ["jazz", "utah"],
            "washington wizards": ["wizards", "washington"],
        }

        for team in standings:
            team_lower = team["team_name"].lower()

            if name_lower in team_lower or team_lower in name_lower:
                return team

            for canonical, aliases in name_map.items():
                name_matches = any(a in name_lower for a in aliases) or canonical in name_lower
                team_matches = any(a in team_lower for a in aliases) or canonical in team_lower
                if name_matches and team_matches:
                    return team

        logger.warning(f"Equipo NBA no encontrado en standings: {team_name}")
        return None

    def get_top_scorers(self) -> list[dict]:
        """NBA no usa goleadores individuales para el modelo."""
        return []

    def get_players_for_match(self, home_team: str, away_team: str, scorers: list[dict]) -> dict:
        """No aplica para el modelo NBA actual."""
        return {"home": [], "away": []}

    def _get_mock_standings(self) -> list[dict]:
        """Datos simulados basados en standings NBA 2025-26 (~70 partidos jugados)."""
        logger.info("Usando standings NBA simulados (modo desarrollo)")

        teams = [
            ("Cleveland Cavaliers", 52, 18, 8120, 7490, "East", 98.5),
            ("Boston Celtics", 50, 20, 8190, 7560, "East", 100.2),
            ("New York Knicks", 47, 23, 7910, 7420, "East", 97.8),
            ("Milwaukee Bucks", 44, 26, 8050, 7700, "East", 101.5),
            ("Indiana Pacers", 43, 27, 8330, 8050, "East", 103.2),
            ("Orlando Magic", 42, 28, 7560, 7280, "East", 96.5),
            ("Miami Heat", 39, 31, 7770, 7630, "East", 97.2),
            ("Philadelphia 76ers", 37, 33, 7700, 7630, "East", 98.8),
            ("Chicago Bulls", 34, 36, 7770, 7840, "East", 99.5),
            ("Atlanta Hawks", 33, 37, 7910, 8050, "East", 101.0),
            ("Brooklyn Nets", 30, 40, 7560, 7840, "East", 98.0),
            ("Toronto Raptors", 28, 42, 7630, 7980, "East", 99.2),
            ("Detroit Pistons", 26, 44, 7420, 7910, "East", 97.5),
            ("Charlotte Hornets", 24, 46, 7490, 7980, "East", 100.5),
            ("Washington Wizards", 18, 52, 7280, 8190, "East", 99.8),
            ("Oklahoma City Thunder", 54, 16, 8260, 7350, "West", 99.0),
            ("Denver Nuggets", 48, 22, 8120, 7560, "West", 98.2),
            ("Minnesota Timberwolves", 46, 24, 7770, 7280, "West", 96.8),
            ("Dallas Mavericks", 44, 26, 8050, 7700, "West", 100.5),
            ("Phoenix Suns", 43, 27, 7980, 7630, "West", 99.5),
            ("Los Angeles Lakers", 42, 28, 7910, 7630, "West", 99.0),
            ("Sacramento Kings", 40, 30, 7980, 7840, "West", 101.8),
            ("Houston Rockets", 39, 31, 7770, 7560, "West", 98.5),
            ("Golden State Warriors", 38, 32, 7840, 7770, "West", 100.0),
            ("Memphis Grizzlies", 36, 34, 7700, 7700, "West", 100.8),
            ("Los Angeles Clippers", 34, 36, 7560, 7700, "West", 97.5),
            ("New Orleans Pelicans", 31, 39, 7630, 7910, "West", 99.5),
            ("San Antonio Spurs", 29, 41, 7630, 7980, "West", 100.2),
            ("Portland Trail Blazers", 25, 45, 7420, 7980, "West", 98.8),
            ("Utah Jazz", 22, 48, 7350, 8120, "West", 99.0),
        ]

        standings = []
        for i, (name, w, l, pf, pa, conf, pace) in enumerate(teams, 1):
            played = w + l
            standings.append({
                "team_id": 2000 + i,
                "team_name": name,
                "rank": i,
                "played": played,
                "wins": w,
                "losses": l,
                "points_for": pf,
                "points_against": pa,
                "point_diff": pf - pa,
                "win_pct": round(w / played, 3) if played > 0 else 0,
                "streak": 0,
                "form": "",
                "conference": conf,
                "pace": pace,
                "std_dev_factor": 1.0,
                "ppg": round(pf / played, 1) if played > 0 else 0,
                "opp_ppg": round(pa / played, 1) if played > 0 else 0,
            })

        return standings
