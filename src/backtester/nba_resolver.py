"""
WinStake.ia — Backtesting Automático NBA (Improvement 7)
Resuelve picks pendientes consultando resultados reales en match_outcomes.
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _migrate_backtesting_columns(conn: sqlite3.Connection) -> None:
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


def _fetch_game_result_from_db(
    conn: sqlite3.Connection,
    home_team: str,
    away_team: str,
    commence_time: str,
) -> Optional[dict]:
    """
    Lee el resultado final de match_outcomes.
    Devuelve {"home_pts": int, "away_pts": int} o None si no existe el partido.
    """
    game_date = commence_time[:10]  # 'YYYY-MM-DD'
    row = conn.execute(
        """SELECT home_score, away_score
           FROM match_outcomes
           WHERE home_team = ? AND away_team = ? AND game_date = ?""",
        (home_team, away_team, game_date),
    ).fetchone()

    if row is None:
        logger.info(f"No games found for {home_team} vs {away_team} on {game_date}")
        return None

    return {"home_pts": row[0], "away_pts": row[1]}


def _void_stale_pending(conn: sqlite3.Connection, days_threshold: int = 14) -> int:
    """
    Marca como VOID picks pendientes cuyo commence_time supera el umbral de días.
    Llamar DESPUÉS del bucle de resolución para no anular picks que sí tienen outcome.
    """
    cutoff_iso = (datetime.now(tz=None) - timedelta(days=days_threshold)).isoformat()
    now_str = datetime.now().isoformat()

    cur = conn.execute(
        """UPDATE value_bets
           SET result = 'VOID',
               pnl_units = 0,
               settled_at = ?
           WHERE sport = 'nba'
             AND is_paper = 1
             AND result IS NULL
             AND analysis_id IN (
               SELECT id FROM analyses
               WHERE commence_time < ?
             )""",
        (now_str, cutoff_iso),
    )
    conn.commit()
    return cur.rowcount


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
    Consulta picks NBA de >24h sin resultado, resuelve desde match_outcomes,
    y voidea los que llevan >14 días pendientes sin outcome disponible.
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

        pending = conn.execute("""
            SELECT
                vb.id as bet_id,
                vb.selection,
                vb.odds,
                vb.stake_units,
                vb.line,
                a.home_team,
                a.away_team,
                a.commence_time,
                a.sport
            FROM value_bets vb
            JOIN analyses a ON vb.analysis_id = a.id
            LEFT JOIN match_results mr ON mr.value_bet_id = vb.id
            WHERE mr.id IS NULL
              AND vb.result IS NULL
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

            result_data = _fetch_game_result_from_db(conn, home_team, away_team, commence_time)
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
            """, (bet_id, home_pts, away_pts, bet_won, profit, now_str, actual_score, now_str))

            conn.execute(
                "UPDATE value_bets SET result = ?, pnl_units = ?, settled_at = ? WHERE id = ?",
                (result, profit, now_str, bet_id),
            )

            conn.commit()
            resolved += 1
            logger.info(
                f"Resuelto bet #{bet_id}: {home_team} vs {away_team} "
                f"({actual_score}) → {selection} = {result} | profit: {profit:+.2f}u"
            )

        # VOID picks sin outcome tras el umbral de días (ejecutar después de intentar resolver)
        voided = _void_stale_pending(conn)
        if voided > 0:
            logger.info(f"Marcados como VOID {voided} picks > 14 días pendientes")

        conn.close()

    except Exception as e:
        logger.error(f"Error en backtesting check: {e}", exc_info=True)
        errors += 1

    summary = {"resolved": resolved, "skipped": skipped, "errors": errors}
    logger.info(f"Backtesting completado: {summary}")
    return summary


def get_backtesting_summary(db_path: str) -> dict:
    """Returns a summary of auto-resolved backtesting results."""
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
