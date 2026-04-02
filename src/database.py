"""
WinStake.ia — Persistencia de Datos (SQLite)
Almacena historial de análisis, value bets y resultados reales.
"""

import sqlite3
import logging
import os
from datetime import datetime
from typing import Optional

from src.analyzer import MatchAnalysis

logger = logging.getLogger(__name__)

# Ruta de la base de datos
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "winstake.db")


class Database:
    """Gestiona la persistencia en SQLite para WinStake.ia."""

    def __init__(self, db_path: str = DB_PATH):
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Crea una conexión con row_factory para acceso por nombre."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        """Crea las tablas si no existen."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_date        TEXT    NOT NULL,
                    home_team       TEXT    NOT NULL,
                    away_team       TEXT    NOT NULL,
                    commence_time   TEXT,
                    lambda_home     REAL,
                    lambda_away     REAL,
                    prob_home       REAL,
                    prob_draw       REAL,
                    prob_away       REAL,
                    prob_over25     REAL,
                    prob_under25    REAL,
                    odds_home       REAL,
                    odds_draw       REAL,
                    odds_away       REAL,
                    odds_over25     REAL,
                    odds_under25    REAL,
                    recommendation  TEXT,
                    confidence      TEXT
                );

                CREATE TABLE IF NOT EXISTS value_bets (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    analysis_id     INTEGER NOT NULL,
                    selection       TEXT    NOT NULL,
                    probability     REAL,
                    odds            REAL,
                    ev_percent      REAL,
                    kelly_full      REAL,
                    kelly_half      REAL,
                    stake_units     REAL,
                    confidence      TEXT,
                    FOREIGN KEY (analysis_id) REFERENCES analyses(id)
                );

                CREATE TABLE IF NOT EXISTS match_results (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    value_bet_id        INTEGER NOT NULL,
                    actual_home_goals   INTEGER,
                    actual_away_goals   INTEGER,
                    bet_won             INTEGER,
                    profit_units        REAL,
                    recorded_at         TEXT NOT NULL,
                    FOREIGN KEY (value_bet_id) REFERENCES value_bets(id)
                );

                CREATE INDEX IF NOT EXISTS idx_analyses_date_teams
                    ON analyses(run_date, home_team, away_team);

                CREATE INDEX IF NOT EXISTS idx_value_bets_analysis
                    ON value_bets(analysis_id);

                CREATE INDEX IF NOT EXISTS idx_match_results_bet
                    ON match_results(value_bet_id);
            """)
            conn.commit()
            logger.info(f"✅ Base de datos inicializada en {self.db_path}")
        finally:
            conn.close()

    # ── Guardar datos ─────────────────────────────────────────

    def save_analysis(self, analysis: MatchAnalysis) -> int:
        """
        Guarda un análisis completo y sus value bets asociadas.
        Retorna el ID del análisis insertado.
        """
        conn = self._get_conn()
        try:
            conn.execute("BEGIN")

            p = analysis.probabilities
            odds = analysis.market_odds

            cursor = conn.execute("""
                INSERT INTO analyses (
                    run_date, home_team, away_team, commence_time,
                    lambda_home, lambda_away,
                    prob_home, prob_draw, prob_away, prob_over25, prob_under25,
                    odds_home, odds_draw, odds_away, odds_over25, odds_under25,
                    recommendation, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                analysis.home_team,
                analysis.away_team,
                analysis.commence_time,
                p.lambda_home,
                p.lambda_away,
                p.home_win,
                p.draw,
                p.away_win,
                p.over_25,
                p.under_25,
                odds.get("home"),
                odds.get("draw"),
                odds.get("away"),
                odds.get("over_25"),
                odds.get("under_25"),
                analysis.recommendation,
                analysis.confidence,
            ))

            analysis_id = cursor.lastrowid

            # Guardar value bets asociadas
            if analysis.best_bet and analysis.best_bet.is_value:
                kelly = analysis.kelly
                conn.execute("""
                    INSERT INTO value_bets (
                        analysis_id, selection, probability, odds,
                        ev_percent, kelly_full, kelly_half, stake_units, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    analysis_id,
                    analysis.best_bet.selection,
                    analysis.best_bet.probability,
                    analysis.best_bet.odds,
                    analysis.best_bet.ev_percent,
                    kelly.kelly_full if kelly else 0,
                    kelly.kelly_half if kelly else 0,
                    kelly.stake_units if kelly else 0,
                    analysis.confidence,
                ))

            conn.commit()
            return analysis_id

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ── Registrar resultados reales ───────────────────────────

    def record_result(
        self,
        value_bet_id: int,
        home_goals: int,
        away_goals: int,
    ) -> float:
        """
        Registra el resultado real de un partido y calcula profit/loss.
        Retorna el profit en unidades.
        """
        conn = self._get_conn()
        try:
            # Obtener la value bet
            row = conn.execute(
                "SELECT selection, odds, stake_units FROM value_bets WHERE id = ?",
                (value_bet_id,)
            ).fetchone()

            if not row:
                logger.error(f"❌ Value bet {value_bet_id} no encontrada")
                return 0.0

            selection = row["selection"]
            odds = row["odds"]
            stake = row["stake_units"]

            # Determinar si ganó
            bet_won = self._check_bet_won(selection, home_goals, away_goals)
            profit = (stake * (odds - 1)) if bet_won else -stake

            conn.execute("""
                INSERT INTO match_results (
                    value_bet_id, actual_home_goals, actual_away_goals,
                    bet_won, profit_units, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                value_bet_id, home_goals, away_goals,
                1 if bet_won else 0, round(profit, 2),
                datetime.now().isoformat(),
            ))
            conn.commit()

            icon = "✅" if bet_won else "❌"
            logger.info(f"{icon} Resultado registrado: bet #{value_bet_id} → {profit:+.1f}u")
            return profit

        finally:
            conn.close()

    @staticmethod
    def _check_bet_won(selection: str, home_goals: int, away_goals: int) -> bool:
        """Determina si una apuesta ganó basándose en el resultado real."""
        sel = selection.lower()
        if sel == "local":
            return home_goals > away_goals
        elif sel == "empate":
            return home_goals == away_goals
        elif sel == "visitante":
            return home_goals < away_goals
        elif sel == "over 2.5":
            return (home_goals + away_goals) > 2
        elif sel == "under 2.5":
            return (home_goals + away_goals) < 3
        return False

    # ── Consultas de ROI ──────────────────────────────────────

    def get_roi_summary(self) -> dict:
        """Calcula el ROI global basado en resultados registrados."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN mr.bet_won = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN mr.bet_won = 0 THEN 1 ELSE 0 END) as losses,
                    SUM(mr.profit_units) as total_profit,
                    SUM(vb.stake_units) as total_staked,
                    AVG(vb.ev_percent) as avg_ev
                FROM match_results mr
                JOIN value_bets vb ON mr.value_bet_id = vb.id
            """).fetchone()

            total_bets = rows["total_bets"] or 0
            total_staked = rows["total_staked"] or 0
            total_profit = rows["total_profit"] or 0

            return {
                "total_bets": total_bets,
                "wins": rows["wins"] or 0,
                "losses": rows["losses"] or 0,
                "win_rate": (rows["wins"] or 0) / total_bets * 100 if total_bets > 0 else 0,
                "total_staked": round(total_staked, 1),
                "total_profit": round(total_profit, 1),
                "roi_percent": round(total_profit / total_staked * 100, 2) if total_staked > 0 else 0,
                "avg_ev": round(rows["avg_ev"] or 0, 2),
            }
        finally:
            conn.close()

    def get_pending_results(self) -> list[dict]:
        """Obtiene value bets sin resultado registrado (pendientes de verificar)."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT
                    vb.id as bet_id,
                    a.home_team,
                    a.away_team,
                    a.commence_time,
                    vb.selection,
                    vb.odds,
                    vb.ev_percent,
                    vb.stake_units
                FROM value_bets vb
                JOIN analyses a ON vb.analysis_id = a.id
                LEFT JOIN match_results mr ON mr.value_bet_id = vb.id
                WHERE mr.id IS NULL
                ORDER BY a.commence_time
            """).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_recent_analyses(self, limit: int = 20) -> list[dict]:
        """Obtiene los análisis más recientes."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT
                    a.*,
                    vb.selection as bet_selection,
                    vb.ev_percent as bet_ev,
                    vb.stake_units as bet_stake
                FROM analyses a
                LEFT JOIN value_bets vb ON vb.analysis_id = a.id
                ORDER BY a.run_date DESC
                LIMIT ?
            """, (limit,)).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_stats_by_selection(self) -> list[dict]:
        """ROI desglosado por tipo de selección (Local, Empate, Visitante, etc.)."""
        conn = self._get_conn()
        try:
            rows = conn.execute("""
                SELECT
                    vb.selection,
                    COUNT(*) as total,
                    SUM(CASE WHEN mr.bet_won = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(mr.profit_units) as profit,
                    SUM(vb.stake_units) as staked,
                    AVG(vb.ev_percent) as avg_ev
                FROM value_bets vb
                JOIN match_results mr ON mr.value_bet_id = vb.id
                GROUP BY vb.selection
                ORDER BY profit DESC
            """).fetchall()

            return [dict(row) for row in rows]
        finally:
            conn.close()
