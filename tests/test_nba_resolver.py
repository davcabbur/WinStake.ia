"""
Tests de integración para nba_resolver.run_backtesting_check().
Verifican que tras resolver un pick se escriben result, pnl_units
y settled_at en value_bets, y que el VOID automático funciona.
"""

import sqlite3
import pytest
from datetime import datetime, timedelta

from src.backtester.nba_resolver import run_backtesting_check


def _build_db(tmp_path):
    """Crea BD mínima con schema real y devuelve (db_path, conn)."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE analyses (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date      TEXT NOT NULL,
            home_team     TEXT NOT NULL,
            away_team     TEXT NOT NULL,
            commence_time TEXT,
            sport         TEXT NOT NULL DEFAULT 'nba'
        );
        CREATE TABLE value_bets (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id   INTEGER NOT NULL,
            sport         TEXT NOT NULL,
            selection     TEXT,
            probability   REAL,
            odds          REAL,
            ev_percent    REAL,
            kelly_full    REAL,
            kelly_half    REAL,
            stake_units   REAL,
            confidence    TEXT,
            line          REAL,
            bookmaker     TEXT,
            odds_at_pick  REAL,
            is_paper      INTEGER DEFAULT 1,
            created_at    TEXT,
            result        TEXT,
            pnl_units     REAL,
            settled_at    TEXT
        );
        CREATE TABLE match_results (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            value_bet_id      INTEGER NOT NULL,
            actual_home_goals INTEGER,
            actual_away_goals INTEGER,
            bet_won           INTEGER,
            profit_units      REAL,
            recorded_at       TEXT NOT NULL,
            actual_score      TEXT,
            resolved_at       TEXT,
            FOREIGN KEY (value_bet_id) REFERENCES value_bets(id)
        );
        CREATE TABLE match_outcomes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            home_team   TEXT NOT NULL,
            away_team   TEXT NOT NULL,
            game_date   TEXT NOT NULL,
            home_score  INTEGER,
            away_score  INTEGER,
            total_score INTEGER,
            winner      TEXT,
            fetched_at  TEXT,
            source      TEXT
        );
    """)
    conn.commit()
    return db_path, conn


def _insert_pick(conn, home_team, away_team, selection, odds, stake, line=None, hours_ago=26):
    """Inserta un análisis + pick pendiente."""
    old_date = (datetime.now() - timedelta(hours=hours_ago)).isoformat()
    conn.execute(
        "INSERT INTO analyses (run_date, home_team, away_team, commence_time, sport) "
        "VALUES (?, ?, ?, ?, 'nba')",
        (old_date, home_team, away_team, old_date),
    )
    analysis_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO value_bets "
        "(analysis_id, sport, selection, odds, stake_units, line, is_paper, probability, ev_percent) "
        "VALUES (?, 'nba', ?, ?, ?, ?, 1, 0.55, 5.0)",
        (analysis_id, selection, odds, stake, line),
    )
    bet_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return bet_id


def _insert_outcome(conn, home_team, away_team, game_date, home_score, away_score):
    """Inserta un resultado en match_outcomes."""
    total = home_score + away_score
    winner = "home" if home_score > away_score else "away"
    conn.execute(
        "INSERT INTO match_outcomes "
        "(home_team, away_team, game_date, home_score, away_score, total_score, winner) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (home_team, away_team, game_date, home_score, away_score, total, winner),
    )
    conn.commit()


# ─── Tests de resolución normal ──────────────────────────────────────────────

def test_win_writes_pnl_and_settled_at(tmp_path):
    """Over 215.5 con score 120-105 = total 225 → WIN."""
    db_path, conn = _build_db(tmp_path)
    game_date = (datetime.now() - timedelta(hours=26)).strftime("%Y-%m-%d")
    bet_id = _insert_pick(conn, "Lakers", "Celtics", "Over", odds=1.91, stake=5.0, line=215.5)
    _insert_outcome(conn, "Lakers", "Celtics", game_date, 120, 105)
    conn.close()

    run_backtesting_check(db_path)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT result, pnl_units, settled_at FROM value_bets WHERE id = ?", (bet_id,)
    ).fetchone()
    conn.close()

    assert row[0] == "WIN"
    assert row[1] == pytest.approx(5.0 * (1.91 - 1), rel=1e-4)  # 4.55
    assert row[2] is not None
    datetime.fromisoformat(row[2])


def test_loss_writes_negative_pnl_and_settled_at(tmp_path):
    """Under 215.5 con score 120-105 = total 225 → LOSS."""
    db_path, conn = _build_db(tmp_path)
    game_date = (datetime.now() - timedelta(hours=26)).strftime("%Y-%m-%d")
    bet_id = _insert_pick(conn, "Lakers", "Celtics", "Under", odds=1.91, stake=5.0, line=215.5)
    _insert_outcome(conn, "Lakers", "Celtics", game_date, 120, 105)
    conn.close()

    run_backtesting_check(db_path)

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT result, pnl_units, settled_at FROM value_bets WHERE id = ?", (bet_id,)
    ).fetchone()
    conn.close()

    assert row[0] == "LOSS"
    assert row[1] == pytest.approx(-5.0)
    assert row[2] is not None
    datetime.fromisoformat(row[2])


# ─── Tests de VOID automático ─────────────────────────────────────────────────

def test_void_stale_pending_marks_old_picks(tmp_path):
    """Picks con commence_time > 14 días sin outcome disponible → VOID."""
    db_path, conn = _build_db(tmp_path)
    bet_id_1 = _insert_pick(conn, "Team A", "Team B", "Home", odds=1.90, stake=5.0, hours_ago=20 * 24)
    bet_id_2 = _insert_pick(conn, "Team C", "Team D", "Away", odds=2.00, stake=3.0, hours_ago=16 * 24)
    conn.close()

    run_backtesting_check(db_path)

    conn = sqlite3.connect(db_path)
    row1 = conn.execute("SELECT result, pnl_units FROM value_bets WHERE id = ?", (bet_id_1,)).fetchone()
    row2 = conn.execute("SELECT result, pnl_units FROM value_bets WHERE id = ?", (bet_id_2,)).fetchone()
    conn.close()

    assert row1[0] == "VOID"
    assert row1[1] == 0
    assert row2[0] == "VOID"
    assert row2[1] == 0


def test_void_stale_pending_ignores_recent(tmp_path):
    """Picks con commence_time < 14 días sin outcome → no se tocan (result sigue NULL)."""
    db_path, conn = _build_db(tmp_path)
    bet_id = _insert_pick(conn, "Team A", "Team B", "Home", odds=1.90, stake=5.0, hours_ago=5 * 24)
    conn.close()

    run_backtesting_check(db_path)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT result FROM value_bets WHERE id = ?", (bet_id,)).fetchone()
    conn.close()

    assert row[0] is None


def test_void_stale_pending_ignores_resolved(tmp_path):
    """Pick ya resuelto como WIN no debe sobreescribirse como VOID aunque sea antiguo."""
    db_path, conn = _build_db(tmp_path)
    game_date = (datetime.now() - timedelta(days=20)).strftime("%Y-%m-%d")
    bet_id = _insert_pick(
        conn, "Lakers", "Celtics", "Over", odds=1.91, stake=5.0, line=215.5, hours_ago=20 * 24
    )
    _insert_outcome(conn, "Lakers", "Celtics", game_date, 120, 105)
    conn.close()

    run_backtesting_check(db_path)

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT result FROM value_bets WHERE id = ?", (bet_id,)).fetchone()
    conn.close()

    assert row[0] == "WIN"
