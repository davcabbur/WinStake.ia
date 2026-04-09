"""
WinStake.ia — Backtesting Automático NBA (Improvement 7)
Resuelve picks pendientes consultando resultados reales via nba_api.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

NBA_SEASON = "2025-26"


def _migrate_backtesting_columns(conn: sqlite3.Connection) -> None:
    """
    Adds backtesting columns to value_bets and match_results if they don't exist.
    Columns: result (WIN/LOSS/PUSH), actual_score, resolved_at.
    """
    vb_cols = [row[1] for row in conn.execute("PRAGMA table_info(value_bets)").fetchall()]
    mr_cols = [row[1] for row in conn.execute("PRAGMA table_info(match_results)").fetchall()]

    if "result" not in vb_cols:
        conn.execute("ALTER TABLE value_bets ADD COLUMN result TEXT")
        logger.info("Migración: columna 'result' añadida a value_bets")

    if "actual_score" not in mr_cols:
        conn.execute("ALTER TABLE match_results ADD COLUMN actual_score TEXT")
        logger.info("Migración: columna 'actual_score' añadida a match_results")

    if "resolved_at" not in mr_cols:
        conn.execute("ALTER TABLE match_results ADD COLUMN resolved_at TEXT")
        logger.info("Migración: columna 'resolved_at' añadida a match_results")

    conn.commit()


def _fetch_game_result_from_nba_api(home_team: str, away_team: str, game_date: str) -> Optional[dict]:
    """
    Tries to find the final score for a game using leaguegamefinder.
    Returns {"home_pts": int, "away_pts": int} or None if not found.
    """
    import time
    try:
        from nba_api.stats.endpoints import leaguegamefinder
        from nba_api.stats.static import teams as nba_teams

        # Find team IDs
        all_teams = nba_teams.get_teams()

        def find_team_id(name: str) -> Optional[int]:
            name_low = name.lower()
            for t in all_teams:
                if (t["full_name"].lower() in name_low or
                        name_low in t["full_name"].lower() or
                        t["nickname"].lower() in name_low):
                    return t["id"]
            return None

        home_id = find_team_id(home_team)
        if not home_id:
            logger.warning(f"No team ID found for: {home_team}")
            return None

        # Search games for home team around the game date
        try:
            date_from = (datetime.strptime(game_date[:10], "%Y-%m-%d") - timedelta(days=1)).strftime("%m/%d/%Y")
            date_to = (datetime.strptime(game_date[:10], "%Y-%m-%d") + timedelta(days=1)).strftime("%m/%d/%Y")
        except (ValueError, TypeError):
            logger.warning(f"Invalid game_date format: {game_date}")
            return None

        time.sleep(0.6)
        finder = leaguegamefinder.LeagueGameFinder(
            team_id_nullable=home_id,
            date_from_nullable=date_from,
            date_to_nullable=date_to,
            season_nullable=NBA_SEASON,
        )
        df = finder.get_data_frames()[0]
        if df.empty:
            logger.info(f"No games found for {home_team} around {game_date}")
            return None

        # Find the away team match
        away_low = away_team.lower().split()[-1]  # use last word (team nickname)
        for _, row in df.iterrows():
            matchup = str(row.get("MATCHUP", ""))
            if away_low in matchup.lower() or "vs." in matchup:
                pts = int(row.get("PTS", 0))
                pm = int(row.get("PLUS_MINUS", 0)) if str(row.get("PLUS_MINUS", "nan")) != "nan" else 0
                opp_pts = pts - pm
                is_home = "vs." in matchup
                if is_home:
                    return {"home_pts": pts, "away_pts": opp_pts}
                else:
                    return {"home_pts": opp_pts, "away_pts": pts}

        return None

    except Exception as e:
        logger.warning(f"Error fetching NBA result for {home_team} vs {away_team}: {e}")
        return None


def _determine_result(selection: str, home_pts: int, away_pts: int, line: Optional[float]) -> str:
    """Returns WIN, LOSS, or PUSH for a given bet selection and actual scores."""
    sel = selection.lower().strip()
    total = home_pts + away_pts
    home_win = home_pts > away_pts
    away_win = home_pts < away_pts

    if sel == "home":
        return "WIN" if home_win else "LOSS"
    elif sel == "away":
        return "WIN" if away_win else "LOSS"
    elif sel == "spread home":
        if line is not None:
            adj = home_pts + line
            if adj > away_pts:
                return "WIN"
            elif adj == away_pts:
                return "PUSH"
            return "LOSS"
        return "WIN" if home_win else "LOSS"
    elif sel == "spread away":
        if line is not None:
            adj = away_pts + line
            if adj > home_pts:
                return "WIN"
            elif adj == home_pts:
                return "PUSH"
            return "LOSS"
        return "WIN" if away_win else "LOSS"
    elif sel == "over":
        if line is not None:
            if total > line:
                return "WIN"
            elif total == line:
                return "PUSH"
            return "LOSS"
        return "WIN" if total > 220 else "LOSS"
    elif sel == "under":
        if line is not None:
            if total < line:
                return "WIN"
            elif total == line:
                return "PUSH"
            return "LOSS"
        return "WIN" if total < 220 else "LOSS"

    return "LOSS"


def run_backtesting_check(db_path: str) -> dict:
    """
    Improvement 7: Query SQLite for picks from >24h ago where result is NULL,
    fetch actual scores from nba_api, and update results.

    Returns a summary dict with counts resolved.
    """
    resolved = 0
    errors = 0
    skipped = 0

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")

        _migrate_backtesting_columns(conn)

        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()

        # Find NBA value bets with no result recorded, from >24h ago
        pending = conn.execute("""
            SELECT
                vb.id as bet_id,
                vb.selection,
                vb.odds,
                vb.stake_units,
                vb.line,
                vb.result,
                a.home_team,
                a.away_team,
                a.commence_time,
                a.sport
            FROM value_bets vb
            JOIN analyses a ON vb.analysis_id = a.id
            LEFT JOIN match_results mr ON mr.value_bet_id = vb.id
            WHERE mr.id IS NULL
              AND a.run_date < ?
              AND a.sport = 'nba'
        """, (cutoff,)).fetchall()

        logger.info(f"Backtesting: {len(pending)} NBA bets pending resolution")

        for row in pending:
            bet_id = row["bet_id"]
            home_team = row["home_team"]
            away_team = row["away_team"]
            commence_time = row["commence_time"] or ""
            selection = row["selection"]
            odds = row["odds"]
            stake = row["stake_units"]
            line = row["line"]

            # Try to fetch actual result
            result_data = _fetch_game_result_from_nba_api(home_team, away_team, commence_time)
            if not result_data:
                skipped += 1
                continue

            home_pts = result_data["home_pts"]
            away_pts = result_data["away_pts"]
            result = _determine_result(selection, home_pts, away_pts, line)
            actual_score = f"{home_pts}-{away_pts}"

            bet_won = 1 if result == "WIN" else 0
            profit = round(stake * (odds - 1), 2) if bet_won else round(-stake, 2)
            if result == "PUSH":
                profit = 0.0

            now_str = datetime.now().isoformat()

            conn.execute("""
                INSERT INTO match_results (
                    value_bet_id, actual_home_goals, actual_away_goals,
                    bet_won, profit_units, recorded_at, actual_score, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                bet_id,
                home_pts,
                away_pts,
                bet_won,
                profit,
                now_str,
                actual_score,
                now_str,
            ))

            # Update result column on value_bets
            conn.execute(
                "UPDATE value_bets SET result = ? WHERE id = ?",
                (result, bet_id)
            )

            conn.commit()
            resolved += 1
            logger.info(
                f"Resuelto bet #{bet_id}: {home_team} vs {away_team} "
                f"({actual_score}) → {selection} = {result} | profit: {profit:+.2f}u"
            )

        conn.close()

    except Exception as e:
        logger.error(f"Error en backtesting check: {e}", exc_info=True)
        errors += 1

    summary = {"resolved": resolved, "skipped": skipped, "errors": errors}
    logger.info(f"Backtesting completado: {summary}")
    return summary


def get_backtesting_summary(db_path: str) -> dict:
    """
    Returns a summary of auto-resolved backtesting results.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        rows = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN vb.result = 'WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN vb.result = 'LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN vb.result = 'PUSH' THEN 1 ELSE 0 END) as pushes,
                SUM(mr.profit_units) as total_profit
            FROM value_bets vb
            JOIN match_results mr ON mr.value_bet_id = vb.id
            WHERE vb.result IS NOT NULL
              AND vb.sport = 'nba'
        """).fetchone()
        conn.close()

        total = rows["total"] or 0
        return {
            "total": total,
            "wins": rows["wins"] or 0,
            "losses": rows["losses"] or 0,
            "pushes": rows["pushes"] or 0,
            "win_rate": round((rows["wins"] or 0) / total * 100, 1) if total > 0 else 0.0,
            "total_profit": round(rows["total_profit"] or 0, 2),
        }
    except Exception as e:
        logger.error(f"Error obteniendo resumen de backtesting: {e}")
        return {}
