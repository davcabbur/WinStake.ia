"""
WinStake.ia — Persistencia de Datos (SQLite)
Almacena historial de análisis, value bets y resultados reales.
"""

import sqlite3
import logging
import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from src.analyzer import MatchAnalysis
from src.ev_calculator import EVCalculator, KellyResult

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

    @contextmanager
    def _get_conn(self):
        """Crea una conexión con row_factory para acceso por nombre."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Crea las tablas si no existen."""
        with self._get_conn() as conn:
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
                    line            REAL,
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

                -- Improvement 8: line movement tracking
                CREATE TABLE IF NOT EXISTS line_snapshots (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id        TEXT,
                    sport           TEXT,
                    snapshot_time   TEXT,
                    spread_line     REAL,
                    total_line      REAL,
                    home_odds       REAL,
                    away_odds       REAL
                );
                CREATE INDEX IF NOT EXISTS idx_line_snapshots_match
                    ON line_snapshots(match_id, snapshot_time);

                CREATE TABLE IF NOT EXISTS engine_settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)

            # Migración: añadir columna sport si no existe (para BD antiguas y nuevas)
            self._migrate_add_sport_column(conn)
            # Poblar settings por defecto si la tabla está vacía
            self._seed_default_settings(conn)
            conn.commit()
            logger.info(f"✅ Base de datos inicializada en {self.db_path}")

    @staticmethod
    def _migrate_add_sport_column(conn: sqlite3.Connection):
        """Migración: añadir columna sport a tablas existentes sin ella."""
        migrated = False
        for table in ("analyses", "value_bets"):
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if "sport" not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN sport TEXT NOT NULL DEFAULT 'laliga'")
                logger.info(f"📦 Migración: columna 'sport' añadida a {table}")
                migrated = True

        vb_cols = [row[1] for row in conn.execute("PRAGMA table_info(value_bets)").fetchall()]
        if "line" not in vb_cols:
            conn.execute("ALTER TABLE value_bets ADD COLUMN line REAL")
            logger.info("📦 Migración: columna 'line' añadida a value_bets")
            migrated = True

        # Crear índices de sport (idempotente)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_sport ON analyses(sport)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_value_bets_sport ON value_bets(sport)")
        if migrated:
            conn.commit()

    # ── Engine settings ───────────────────────────────────────

    _DEFAULT_SETTINGS = {
        "ev_min":          "3.0",
        "kelly_fraction":  "0.5",
        "kelly_cap":       "0.25",
        "home_advantage":  "1.25",
        "xg_weight":       "0.65",
        "bankroll_base":   "100.0",
    }

    @staticmethod
    def _seed_default_settings(conn: sqlite3.Connection):
        """Inserta valores por defecto solo si la tabla está vacía."""
        count = conn.execute("SELECT COUNT(*) FROM engine_settings").fetchone()[0]
        if count == 0:
            conn.executemany(
                "INSERT INTO engine_settings (key, value) VALUES (?, ?)",
                list(Database._DEFAULT_SETTINGS.items()),
            )

    def get_settings(self) -> dict:
        """Devuelve el diccionario de settings del motor."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM engine_settings").fetchall()
            settings = dict(Database._DEFAULT_SETTINGS)  # fallback a defaults
            for row in rows:
                settings[row["key"]] = row["value"]
            return {k: float(v) for k, v in settings.items()}

    def update_settings(self, new_values: dict) -> dict:
        """Actualiza settings del motor y devuelve el estado completo."""
        with self._get_conn() as conn:
            for key, value in new_values.items():
                if key in Database._DEFAULT_SETTINGS:
                    conn.execute(
                        "INSERT INTO engine_settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, str(value)),
                    )
            conn.commit()
        return self.get_settings()

    # ── Guardar datos ─────────────────────────────────────────

    def save_analysis(self, analysis: MatchAnalysis, sport: str = "laliga") -> int:
        """
        Guarda un análisis completo y sus value bets asociadas.
        Retorna el ID del análisis insertado.
        """
        with self._get_conn() as conn:
            try:
                conn.execute("BEGIN")

                p = analysis.probabilities
                odds = analysis.market_odds

                # Extraer campos de forma compatible con ambos modelos
                # Football: MatchProbabilities tiene lambda_home/away, over_25, etc.
                # NBA: NBAMatchProbabilities tiene home_score/away_score, over_total, etc.
                lambda_home = getattr(p, "lambda_home", None) or getattr(p, "home_score", None)
                lambda_away = getattr(p, "lambda_away", None) or getattr(p, "away_score", None)
                prob_draw = getattr(p, "draw", 0.0)
                prob_over25 = getattr(p, "over_25", None) or getattr(p, "over_total", None)
                prob_under25 = getattr(p, "under_25", None) or getattr(p, "under_total", None)

                cursor = conn.execute("""
                    INSERT INTO analyses (
                        run_date, sport, home_team, away_team, commence_time,
                        lambda_home, lambda_away,
                        prob_home, prob_draw, prob_away, prob_over25, prob_under25,
                        odds_home, odds_draw, odds_away, odds_over25, odds_under25,
                        recommendation, confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    datetime.now().isoformat(),
                    sport,
                    analysis.home_team,
                    analysis.away_team,
                    analysis.commence_time,
                    lambda_home,
                    lambda_away,
                    p.home_win,
                    prob_draw,
                    p.away_win,
                    prob_over25,
                    prob_under25,
                    odds.get("home"),
                    odds.get("draw"),
                    odds.get("away"),
                    odds.get("over_25") or odds.get("over"),
                    odds.get("under_25") or odds.get("under"),
                    analysis.recommendation,
                    analysis.confidence,
                ))

                analysis_id = cursor.lastrowid

                # Inicializar calculadora EV una vez por partido
                ev_calc = EVCalculator()

                # Guardar TODAS las value bets del partido
                for ev in analysis.ev_results:
                    if not ev.is_value:
                        continue
                    kelly = ev_calc.kelly_criterion(ev.probability, ev.odds)
                    confidence = self._classify_ev(ev.ev_percent)
                    conn.execute("""
                        INSERT INTO value_bets (
                            analysis_id, sport, selection, probability, odds,
                            ev_percent, kelly_full, kelly_half, stake_units, confidence, line
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        analysis_id,
                        sport,
                        ev.selection,
                        ev.probability,
                        ev.odds,
                        ev.ev_percent,
                        kelly.kelly_full,
                        kelly.kelly_half,
                        kelly.stake_units,
                        confidence,
                        ev.line,
                    ))

                conn.commit()
                return analysis_id

            except Exception:
                conn.rollback()
                raise

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
        with self._get_conn() as conn:
            # Obtener la value bet
            row = conn.execute(
                "SELECT selection, odds, stake_units, line FROM value_bets WHERE id = ?",
                (value_bet_id,)
            ).fetchone()

            if not row:
                logger.error(f"❌ Value bet {value_bet_id} no encontrada")
                return 0.0

            selection = row["selection"]
            odds = row["odds"]
            stake = row["stake_units"]
            line = row["line"]

            # Determinar si ganó
            bet_won = self._check_bet_won(selection, home_goals, away_goals, line)
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

    @staticmethod
    def _classify_ev(ev_percent: float) -> str:
        return EVCalculator.classify_confidence(ev_percent)

    @staticmethod
    def _check_bet_won(selection: str, home_goals: int, away_goals: int, line: Optional[float] = None) -> bool:
        """Determina si una apuesta ganó basándose en el resultado real."""
        sel = selection.lower().strip()
        total = home_goals + away_goals
        home_win = home_goals > away_goals
        draw = home_goals == away_goals
        away_win = home_goals < away_goals

        # 1X2
        if sel == "local":
            return home_win
        elif sel == "empate":
            return draw
        elif sel == "visitante":
            return away_win

        # Doble Oportunidad
        elif sel == "1x":
            return home_win or draw
        elif sel == "x2":
            return draw or away_win
        elif sel == "12":
            return home_win or away_win

        # Over/Under
        elif sel == "over 1.5":
            return total > 1
        elif sel == "under 1.5":
            return total < 2
        elif sel == "over 2.5":
            return total > 2
        elif sel == "under 2.5":
            return total < 3
        elif sel == "over 3.5":
            return total > 3
        elif sel == "under 3.5":
            return total < 4

        # BTTS
        elif sel in ("btts sí", "btts si"):
            return home_goals >= 1 and away_goals >= 1
        elif sel == "btts no":
            return home_goals == 0 or away_goals == 0

        # NBA Moneyline
        elif sel == "home":
            return home_win
        elif sel == "away":
            return away_win

        # NBA Spread
        elif sel == "spread home":
            if line is not None:
                # spread_line is home's handicap. e.g. -5.5
                return (home_goals + line) > away_goals
            return home_win

        elif sel == "spread away":
            if line is not None:
                # line is away's handicap. e.g. if home is -5.5, away line is +5.5 stored in DB
                return (away_goals + line) > home_goals
            return away_win

        # NBA Totals
        elif sel == "over":
            if line is not None:
                return total > line
            return total > 220
        elif sel == "under":
            if line is not None:
                return total < line
            return total < 220

        return False

    # ── Consultas de ROI ──────────────────────────────────────

    def get_roi_summary(self, sport: str = None) -> dict:
        """
        Calcula el ROI basado en resultados registrados.
        Si sport es None, devuelve ROI global de todos los deportes.
        """
        with self._get_conn() as conn:
            query = """
                SELECT
                    COUNT(*) as total_bets,
                    SUM(CASE WHEN mr.bet_won = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN mr.bet_won = 0 THEN 1 ELSE 0 END) as losses,
                    SUM(mr.profit_units) as total_profit,
                    SUM(vb.stake_units) as total_staked,
                    AVG(vb.ev_percent) as avg_ev
                FROM match_results mr
                JOIN value_bets vb ON mr.value_bet_id = vb.id
            """
            params = ()
            if sport:
                query += " WHERE vb.sport = ?"
                params = (sport,)
            rows = conn.execute(query, params).fetchone()

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

    def get_pending_results(self) -> list[dict]:
        """Obtiene value bets sin resultado registrado (pendientes de verificar)."""
        with self._get_conn() as conn:
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

    def get_recent_analyses(self, limit: int = 20) -> list[dict]:
        """Obtiene los análisis más recientes."""
        with self._get_conn() as conn:
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

    # ── Improvement 8: Line movement tracking ────────────────

    def save_line_snapshot(
        self,
        match_id: str,
        sport: str,
        spread_line: Optional[float],
        total_line: Optional[float],
        home_odds: Optional[float],
        away_odds: Optional[float],
    ) -> None:
        """Saves a line snapshot for a given match."""
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO line_snapshots (
                    match_id, sport, snapshot_time, spread_line, total_line, home_odds, away_odds
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                match_id,
                sport,
                datetime.now().isoformat(),
                spread_line,
                total_line,
                home_odds,
                away_odds,
            ))
            conn.commit()

    def detect_line_movement(
        self,
        match_id: str,
        current_spread: Optional[float],
        current_total: Optional[float],
        current_home_odds: Optional[float],
        current_away_odds: Optional[float],
    ) -> Optional[str]:
        """
        Compares current odds vs last snapshot.
        Returns an alert string if significant movement detected, else None.
        Thresholds: |spread_change| >= 2.0 or |total_change| >= 3.0.
        """
        with self._get_conn() as conn:
            last = conn.execute("""
                SELECT spread_line, total_line, home_odds, away_odds, snapshot_time
                FROM line_snapshots
                WHERE match_id = ?
                ORDER BY snapshot_time DESC
                LIMIT 1
            """, (match_id,)).fetchone()

        if not last:
            return None

        alerts = []
        if current_spread is not None and last["spread_line"] is not None:
            delta = abs(current_spread - last["spread_line"])
            if delta >= 2.0:
                alerts.append(
                    f"📈 Spread moved {last['spread_line']:+.1f} → {current_spread:+.1f} "
                    f"(Δ{delta:.1f})"
                )
        if current_total is not None and last["total_line"] is not None:
            delta = abs(current_total - last["total_line"])
            if delta >= 3.0:
                alerts.append(
                    f"📊 Total moved {last['total_line']:.1f} → {current_total:.1f} "
                    f"(Δ{delta:.1f})"
                )

        if alerts:
            return "⚠️ Movimiento de línea detectado: " + " | ".join(alerts)
        return None

    def get_stats_by_selection(self) -> list[dict]:
        """ROI desglosado por tipo de selección (Local, Empate, Visitante, etc.)."""
        with self._get_conn() as conn:
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
