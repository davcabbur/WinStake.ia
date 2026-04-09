"""
WinStake.ia — Cliente de estadísticas NBA
Obtiene standings y stats de equipos usando nba_api (stats.nba.com).
No requiere API key.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from src.cache import APICache
import config

SPAIN_TZ = ZoneInfo("Europe/Madrid")

logger = logging.getLogger(__name__)

NBA_SEASON = "2025-26"

# Mapeo nombre completo → abreviación ESPN (mismas que stats.nba.com)
NBA_ESPN_ABBR: dict[str, str] = {
    "atlanta hawks": "ATL", "boston celtics": "BOS", "brooklyn nets": "BKN",
    "charlotte hornets": "CHA", "chicago bulls": "CHI", "cleveland cavaliers": "CLE",
    "dallas mavericks": "DAL", "denver nuggets": "DEN", "detroit pistons": "DET",
    "golden state warriors": "GSW", "houston rockets": "HOU", "indiana pacers": "IND",
    "los angeles clippers": "LAC", "los angeles lakers": "LAL", "memphis grizzlies": "MEM",
    "miami heat": "MIA", "milwaukee bucks": "MIL", "minnesota timberwolves": "MIN",
    "new orleans pelicans": "NOP", "new york knicks": "NYK", "oklahoma city thunder": "OKC",
    "orlando magic": "ORL", "philadelphia 76ers": "PHI", "phoenix suns": "PHX",
    "portland trail blazers": "POR", "sacramento kings": "SAC", "san antonio spurs": "SAS",
    "toronto raptors": "TOR", "utah jazz": "UTA", "washington wizards": "WAS",
}

# Alias alternativos que puede venir de The Odds API
_ABBR_ALIASES: dict[str, str] = {
    "la lakers": "LAL", "la clippers": "LAC", "gs warriors": "GSW",
    "okc thunder": "OKC", "sa spurs": "SAS", "no pelicans": "NOP",
    "nola pelicans": "NOP", "76ers": "PHI", "sixers": "PHI",
    "blazers": "POR", "trail blazers": "POR", "wolves": "MIN",
    "timberwolves": "MIN", "knicks": "NYK", "nets": "BKN",
    "cavaliers": "CLE", "cavs": "CLE", "bucks": "MIL",
    "celtics": "BOS", "suns": "PHX", "nuggets": "DEN",
    "grizzlies": "MEM", "mavericks": "DAL", "mavs": "DAL",
    "rockets": "HOU", "heat": "MIA", "bulls": "CHI",
    "raptors": "TOR", "hawks": "ATL", "magic": "ORL",
    "pistons": "DET", "hornets": "CHA", "jazz": "UTA",
    "wizards": "WAS", "pacers": "IND", "kings": "SAC",
    "lakers": "LAL", "clippers": "LAC", "warriors": "GSW",
    "thunder": "OKC", "spurs": "SAS", "pelicans": "NOP",
}


class NBAClient:
    """Cliente para estadísticas NBA via nba_api."""

    def __init__(self, api_key: str = None):
        self.cache = APICache()
        self._mock_mode = False
        self._pace_cache: dict[int, float] = {}  # team_id -> pace (in-memory within session)

    # ── Improvement 5: game window helper ────────────────────

    @staticmethod
    def _is_game_window() -> bool:
        """Returns True if current local hour is in typical NBA game window (19:00–02:00)."""
        hour = datetime.now().hour
        return hour >= 19 or hour < 2

    def _dvp_ttl(self) -> int:
        """Dynamic TTL for DvP/player stats: 2h during game window, 24h otherwise."""
        return 7200 if self._is_game_window() else 86400

    def _player_stats_ttl(self) -> int:
        """Dynamic TTL for player stats: 2h during game window, 1h otherwise."""
        return 7200 if self._is_game_window() else 3600

    # ── Improvement 1: real pace via leaguedashteamstats ─────

    def get_team_pace_map(self) -> dict[int, float]:
        """
        Fetches PACE for all NBA teams using leaguedashteamstats.
        Returns {team_id: pace_float}.
        """
        cache_key = f"nba_team_pace_{NBA_SEASON}"
        cached = self.cache.get(cache_key, 86400)
        if cached is not None:
            return {int(k): v for k, v in cached.items()}

        try:
            from nba_api.stats.endpoints import leaguedashteamstats
            time.sleep(0.6)
            raw = leaguedashteamstats.LeagueDashTeamStats(
                season=NBA_SEASON,
                per_mode_simple="PerGame",
            )
            df = raw.get_data_frames()[0]
            result: dict[int, float] = {}
            for _, row in df.iterrows():
                tid = int(row["TEAM_ID"])
                pace = float(row.get("PACE", 100.0)) if row.get("PACE") else 100.0
                result[tid] = round(pace, 2)
            self.cache.set(cache_key, {str(k): v for k, v in result.items()})
            logger.info(f"Pace cargado para {len(result)} equipos NBA")
            return result
        except Exception as e:
            logger.warning(f"Error obteniendo pace NBA: {e}")
            return {}

    # ── Improvement 3: back-to-back detection ────────────────

    def get_back_to_back_teams(self, game_date: str) -> set:
        """
        Returns a set of team_ids that played the day before game_date.
        game_date: 'YYYY-MM-DD' string.
        """
        cache_key = f"nba_b2b_{game_date}_{NBA_SEASON}"
        cached = self.cache.get(cache_key, 86400)
        if cached is not None:
            return set(cached)

        try:
            from nba_api.stats.endpoints import leaguegamelog
            prev_date = (datetime.strptime(game_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%m/%d/%Y")
            time.sleep(0.6)
            log = leaguegamelog.LeagueGameLog(
                season=NBA_SEASON,
                date_from_nullable=prev_date,
                date_to_nullable=prev_date,
            )
            df = log.get_data_frames()[0]
            b2b_ids = set(int(tid) for tid in df["TEAM_ID"].unique()) if not df.empty else set()
            self.cache.set(cache_key, list(b2b_ids))
            logger.info(f"B2B check for {game_date}: {len(b2b_ids)} teams played yesterday")
            return b2b_ids
        except Exception as e:
            logger.warning(f"Error checking back-to-back for {game_date}: {e}")
            return set()

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

            # Improvement 1: fetch real pace for all teams
            pace_map = self.get_team_pace_map()

            result = []
            for _, row in df.iterrows():
                played = int(row["WINS"]) + int(row["LOSSES"])
                ppg = float(row["PointsPG"]) if row["PointsPG"] else 0
                opp_ppg = float(row["OppPointsPG"]) if row["OppPointsPG"] else 0
                tid = int(row["TeamID"])

                result.append({
                    "team_id": tid,
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
                    "pace": pace_map.get(tid, 100.0),  # Improvement 1: real pace
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
                pm_val = game.get("PLUS_MINUS") if hasattr(game, "get") else game["PLUS_MINUS"] if "PLUS_MINUS" in game.index else 0
                plus_minus = int(pm_val) if pm_val and str(pm_val) not in ("", "nan") else 0
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

    def get_player_stats_for_teams(self, team_ids: list[int]) -> dict:
        """
        Obtiene puntos/rebotes/asistencias/triples por jugador para los equipos dados.
        Devuelve {team_id: [{"player_name", "pts_season", "reb_season", "ast_season",
                              "fg3m_season", "pts_l10", "reb_l10", "ast_l10", "fg3m_l10", ...}]}
        Hace 2 llamadas a stats.nba.com: media de temporada + últimos 10 partidos.
        """
        if not team_ids:
            return {}

        # Improvement 5: season-versioned cache key + dynamic TTL
        cache_key = f"nba_player_props_{NBA_SEASON}_v2"
        cached = self.cache.get(cache_key, self._player_stats_ttl())
        if cached is not None:
            # JSON serializa claves int como str — normalizar
            return {tid: cached.get(str(tid), cached.get(tid, [])) for tid in team_ids}

        try:
            from nba_api.stats.endpoints import leaguedashplayerstats

            # 1. Media de temporada completa
            time.sleep(0.6)
            season_raw = leaguedashplayerstats.LeagueDashPlayerStats(
                season=NBA_SEASON,
                per_mode_detailed="PerGame",
                last_n_games=0,
            )
            season_df = season_raw.get_data_frames()[0]

            # 2. Media últimos 10 partidos
            time.sleep(0.6)
            l10_raw = leaguedashplayerstats.LeagueDashPlayerStats(
                season=NBA_SEASON,
                per_mode_detailed="PerGame",
                last_n_games=10,
            )
            l10_df = l10_raw.get_data_frames()[0]

            # Indexar L10 por player_id para búsqueda rápida
            l10_index = {int(row["PLAYER_ID"]): row for _, row in l10_df.iterrows()}

            # Agrupar por team_id
            all_teams: dict[int, list[dict]] = {}
            for _, row in season_df.iterrows():
                tid = int(row["TEAM_ID"])
                pid = int(row["PLAYER_ID"])
                gp = int(row.get("GP", 0))
                if gp < 8:  # Ignorar jugadores con muy pocos partidos
                    continue

                player: dict = {
                    "player_id": pid,
                    "player_name": str(row["PLAYER_NAME"]),
                    "gp_season": gp,
                    "mpg_season": round(float(row.get("MIN", 0)), 1),
                    "pts_season":  round(float(row.get("PTS",  0)), 1),
                    "reb_season":  round(float(row.get("REB",  0)), 1),
                    "ast_season":  round(float(row.get("AST",  0)), 1),
                    "fg3m_season": round(float(row.get("FG3M", 0)), 1),
                    "stl_season":  round(float(row.get("STL",  0)), 1),
                    "blk_season":  round(float(row.get("BLK",  0)), 1),
                }

                l10 = l10_index.get(pid)
                recently_traded = False
                if l10 is not None:
                    pts_l10  = round(float(l10.get("PTS",  0)), 1)
                    reb_l10  = round(float(l10.get("REB",  0)), 1)
                    ast_l10  = round(float(l10.get("AST",  0)), 1)
                    fg3m_l10 = round(float(l10.get("FG3M", 0)), 1)
                    stl_l10  = round(float(l10.get("STL",  0)), 1)
                    blk_l10  = round(float(l10.get("BLK",  0)), 1)

                    # Improvement 4: detect recently-traded players (L10 anomaly)
                    # If gp_season > 20 and L10 pts diverges >50% from season avg, flag as traded
                    pts_season = player["pts_season"]
                    if gp > 20 and pts_season > 0 and pts_l10 > 0:
                        ratio = pts_l10 / pts_season
                        if ratio > 1.5 or ratio < 0.5:
                            recently_traded = True
                            logger.info(
                                f"Possible traded player: {player['player_name']} "
                                f"(season {pts_season} vs L10 {pts_l10}) — using season avg"
                            )
                            # Conservative fallback: use season averages for L10
                            pts_l10  = player["pts_season"]
                            reb_l10  = player["reb_season"]
                            ast_l10  = player["ast_season"]
                            fg3m_l10 = player["fg3m_season"]
                            stl_l10  = player["stl_season"]
                            blk_l10  = player["blk_season"]

                    player.update({
                        "gp_l10":   int(l10.get("GP", 0)),
                        "pts_l10":  pts_l10,
                        "reb_l10":  reb_l10,
                        "ast_l10":  ast_l10,
                        "fg3m_l10": fg3m_l10,
                        "stl_l10":  stl_l10,
                        "blk_l10":  blk_l10,
                        "recently_traded": recently_traded,
                    })
                else:
                    player.update({"gp_l10": 0, "pts_l10": 0.0, "reb_l10": 0.0,
                                   "ast_l10": 0.0, "fg3m_l10": 0.0,
                                   "stl_l10": 0.0, "blk_l10": 0.0,
                                   "recently_traded": False})

                all_teams.setdefault(str(tid), []).append(player)

            # Ordenar por PPG de temporada y guardar en caché (claves str para JSON)
            for k in all_teams:
                all_teams[k].sort(key=lambda p: p["pts_season"], reverse=True)

            self.cache.set(cache_key, all_teams)
            logger.info(f"Player props NBA: {len(all_teams)} equipos cargados")
            return {tid: all_teams.get(str(tid), []) for tid in team_ids}

        except Exception as e:
            logger.warning(f"Error obteniendo player props NBA: {e}")
            return {tid: [] for tid in team_ids}

    def get_defense_vs_position(self, team_id: int) -> dict:
        """
        Retorna cuántos PTS/REB/AST/3PM concede este equipo a cada posición (G/F/C).
        Ejemplo: {"G": {"pts": 28.5, "reb": 4.1, "ast": 6.0, "fg3m": 2.2}, ...}
        """
        # Improvement 5: season-versioned cache key + dynamic TTL
        cache_key = f"nba_dvp_{team_id}_{NBA_SEASON}_v2"
        cached = self.cache.get(cache_key, self._dvp_ttl())
        if cached is not None:
            return cached

        result = {}
        try:
            from nba_api.stats.endpoints import leaguedashplayerstats
            for pos in ("G", "F", "C"):
                time.sleep(0.5)
                r = leaguedashplayerstats.LeagueDashPlayerStats(
                    season=NBA_SEASON,
                    per_mode_detailed="PerGame",
                    opponent_team_id=team_id,
                    player_position_abbreviation_nullable=pos,
                    last_n_games=0,
                    timeout=30,
                )
                df = r.get_data_frames()[0]
                if df.empty:
                    continue
                # Filtrar jugadores con al menos 3 juegos vs este equipo (muestra representativa)
                df = df[df["GP"] >= 2]
                if df.empty:
                    continue
                result[pos] = {
                    "pts":  round(float(df["PTS"].mean()),  1),
                    "reb":  round(float(df["REB"].mean()),  1),
                    "ast":  round(float(df["AST"].mean()),  1),
                    "fg3m": round(float(df["FG3M"].mean()), 1),
                    "stl":  round(float(df["STL"].mean()),  2),
                    "blk":  round(float(df["BLK"].mean()),  2),
                    "games": int(df["GP"].sum()),
                }
            self.cache.set(cache_key, result)
            logger.info(f"DvP cargado para team_id={team_id}: {list(result.keys())}")
        except Exception as e:
            logger.warning(f"Error obteniendo DvP para team_id={team_id}: {e}")
        return result

    def get_team_last10(self, team_id: int) -> list[dict]:
        """Retorna los últimos 10 partidos del equipo con resultado y puntos."""
        cache_key = f"nba_last10_{team_id}_{NBA_SEASON}"
        cached = self.cache.get(cache_key, 21600)
        if cached is not None:
            return cached

        try:
            from nba_api.stats.endpoints import teamgamelog
            time.sleep(0.5)
            log = teamgamelog.TeamGameLog(team_id=team_id, season=NBA_SEASON, timeout=30)
            df = log.get_data_frames()[0].head(10)

            games = []
            for _, row in df.iterrows():
                matchup = str(row["MATCHUP"])
                is_home = "vs." in matchup
                pts = int(row["PTS"])
                wl = str(row["WL"])
                # Estimar puntos rival
                pm_raw = row.get("PLUS_MINUS") if hasattr(row, "get") else None
                if pm_raw is None and "PLUS_MINUS" in row.index:
                    pm_raw = row["PLUS_MINUS"]
                plus_minus = int(pm_raw) if pm_raw is not None and str(pm_raw) not in ("", "nan", "None") else 0
                opp_pts = pts - plus_minus

                opponent = matchup.split("vs. ")[-1] if is_home else matchup.split("@ ")[-1]
                games.append({
                    "date": str(row["GAME_DATE"]),
                    "opponent": opponent.strip(),
                    "home": is_home,
                    "pts": pts,
                    "opp_pts": opp_pts,
                    "win": wl == "W",
                })
            self.cache.set(cache_key, games)
            return games
        except Exception as e:
            logger.warning(f"Error obteniendo últimos 10 partidos team_id={team_id}: {e}")
            return []

    def get_espn_schedule(self, days_ahead: int = 2) -> list[dict]:
        """
        Obtiene calendario NBA desde ESPN Deportes.
        Fuente: https://espndeportes.espn.com/basquetbol/nba/calendario
        Devuelve partidos con horarios en zona horaria de España (Europe/Madrid).
        """
        cache_key = "nba_espn_schedule"
        cached = self.cache.get(cache_key, 1800)
        if cached is not None:
            return cached

        try:
            import httpx
            base_url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
            games = []
            now_utc = datetime.now(timezone.utc)

            for day_offset in range(days_ahead + 1):
                target = now_utc + timedelta(days=day_offset)
                date_str = target.strftime("%Y%m%d")
                resp = httpx.get(base_url, params={"dates": date_str, "lang": "es", "region": "es"}, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                for event in data.get("events", []):
                    competition = event.get("competitions", [{}])[0]
                    competitors = competition.get("competitors", [])
                    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
                    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
                    if not home or not away:
                        continue

                    start_utc_str = event.get("date", "")
                    commence_spain = ""
                    if start_utc_str:
                        try:
                            start_utc = datetime.fromisoformat(start_utc_str.replace("Z", "+00:00"))
                            start_spain = start_utc.astimezone(SPAIN_TZ)
                            commence_spain = start_spain.strftime("%d/%m/%Y %H:%M")
                        except (ValueError, TypeError):
                            pass

                    games.append({
                        "espn_id": event.get("id"),
                        "home_team": home.get("team", {}).get("displayName", ""),
                        "away_team": away.get("team", {}).get("displayName", ""),
                        "home_abbr": home.get("team", {}).get("abbreviation", ""),
                        "away_abbr": away.get("team", {}).get("abbreviation", ""),
                        "commence_time_utc": start_utc_str,
                        "commence_time_spain": commence_spain,
                        "status": event.get("status", {}).get("type", {}).get("description", ""),
                    })

            self.cache.set(cache_key, games)
            logger.info(f"Calendario ESPN Deportes: {len(games)} partidos NBA")
            return games
        except Exception as e:
            logger.warning(f"Error obteniendo calendario ESPN: {e}")
            return []

    def get_injuries(self) -> dict:
        """
        Obtiene lesiones NBA desde ESPN Deportes.
        Fuente: https://espndeportes.espn.com/basquetbol/nba/lesiones
        Retorna {team_abbrev: [{"player", "status", "detail"}]}
        """
        cache_key = "nba_injuries_espn"
        cached = self.cache.get(cache_key, 3600)
        if cached is not None:
            return cached

        try:
            import httpx
            # API pública de ESPN (fuente del calendario espndeportes.espn.com)
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"
            resp = httpx.get(url, params={"lang": "es", "region": "es"}, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            result = {}
            for team_entry in data.get("injuries", []):
                abbr = team_entry.get("team", {}).get("abbreviation", "")
                players = []
                for inj in team_entry.get("injuries", []):
                    athlete = inj.get("athlete", {})
                    details = inj.get("details", {})
                    players.append({
                        "player": athlete.get("displayName", ""),
                        "position": athlete.get("position", {}).get("abbreviation", ""),
                        "status": inj.get("status", ""),
                        "detail": details.get("detail", "") or details.get("type", ""),
                        "return_date": details.get("returnDate", ""),
                        "comment": inj.get("shortComment", ""),
                    })
                if players:
                    result[abbr] = players
            self.cache.set(cache_key, result)
            logger.info(f"Lesiones NBA: {len(result)} equipos con bajas")
            return result
        except Exception as e:
            logger.warning(f"Error obteniendo lesiones NBA: {e}")
            return {}

    def get_player_positions(self, team_id: int) -> dict:
        """
        Retorna {player_id: "G"|"F"|"C"} para el roster actual del equipo.
        """
        cache_key = f"nba_positions_{team_id}_{NBA_SEASON}"
        cached = self.cache.get(cache_key, 86400)
        if cached is not None:
            # JSON convierte claves int a str — devolver con int
            return {int(k): v for k, v in cached.items()}

        try:
            from nba_api.stats.endpoints import commonteamroster
            time.sleep(0.5)
            r = commonteamroster.CommonTeamRoster(team_id=team_id, season=NBA_SEASON, timeout=30)
            df = r.get_data_frames()[0]
            result = {}
            for _, row in df.iterrows():
                pid = int(row["PLAYER_ID"])
                pos_raw = str(row.get("POSITION", "F"))
                # "G-F" → "G", "C-F" → "C", etc.
                primary = pos_raw.split("-")[0].strip().upper()
                result[pid] = primary if primary in ("G", "F", "C") else "F"
            self.cache.set(cache_key, result)
            return result
        except Exception as e:
            logger.warning(f"Error obteniendo posiciones team_id={team_id}: {e}")
            return {}

    @staticmethod
    def get_espn_abbr(team_name: str) -> str:
        """Devuelve la abreviación ESPN estándar de un equipo NBA."""
        lower = team_name.lower().strip()
        # Exact / substring match in full names
        for canonical, abbr in NBA_ESPN_ABBR.items():
            if canonical in lower or lower in canonical:
                return abbr
        # Alias match (single-word nicknames, etc.)
        for alias, abbr in _ABBR_ALIASES.items():
            if alias in lower:
                return abbr
        return ""

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
