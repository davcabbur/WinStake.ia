"""
Tests de integración para nba_resolver.run_backtesting_check().
Verifican que tras resolver un pick se escriben result, pnl_units
y settled_at en value_bets.
"""

import sqlite3
import pytest
from unittest.mock import patch
from datetime import datetime, timedelta

from src.backtester.nba_resolver import run_backtesting_check


def _build_db(tmp_path):
    """Crea BD mínima con schema real y devuelve (db_path, conn)."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE analyses (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date     TEXT NOT NULL,
            home_team    TEXT NOT NULL,
            away_team    TEXT NOT NULL,
            commence_time TEXT,
            sport        TEXT NOT NULL DEFAULT 'nba'
        );
        CREATE TABLE value_bets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id  INTEGER NOT NULL,
            sport        TEXT NOT NULL,
            selection    TEXT,
            probability  REAL,
            odds         REAL,
            ev_percent   REAL,
            kelly_full   REAL,
            kelly_half   REAL,
            stake_units  REAL,
            confidence   TEXT,
            line         REAL,
            bookmaker    TEXT,
            odds_at_pick REAL,
            is_paper     INTEGER DEFAULT 1,
            created_at   TEXT,
            result       TEXT,
            pnl_units    REAL,
            settled_at   TEXT
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
    """)
    conn.commit()
    return db_path, conn


def _insert_pick(conn, home_team, away_team, selection, odds, stake, line=None):
    """Inserta un análisis + pick pendiente (>25h en el pasado)."""
    old_date = (datetime.now() - timedelta(hours=26)).isoformat()
    conn.execute(
        "INSERT INTO analyses (run_date, home_team, away_team, commence_time, sport) "
        "VALUES (?, ?, ?, ?, 'nba')",
        (old_date, home_team, away_team, old_date)
    )
    analysis_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO value_bets "
        "(analysis_id, sport, selection, odds, stake_units, line, is_paper, probability, ev_percent) "
        "VALUES (?, 'nba', ?, ?, ?, ?, 1, 0.55, 5.0)",
        (analysis_id, selection, odds, stake, line)
    )
    bet_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return bet_id


@pytest.fixture
def fake_game_result():
    """Parchea _fetch_game_result_from_nba_api para devolver un score conocido."""
    with patch(
        "src.backtester.nba_resolver._fetch_game_result_from_nba_api",
        return_value={"home_pts": 120, "away_pts": 105},
    ) as mock:
        yield mock


def test_win_writes_pnl_and_settled_at(tmp_path, fake_game_result):
    """Over 215.5 con score 120-105 = total 225 → WIN. Verifica las 3 columnas."""
    db_path, conn = _build_db(tmp_path)
    bet_id = _insert_pick(conn, "Lakers", "Celtics", "Over", odds=1.91, stake=5.0, line=215.5)
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
    datetime.fromisoformat(row[2])  # debe ser ISO válido


def test_loss_writes_negative_pnl_and_settled_at(tmp_path, fake_game_result):
    """Under 215.5 con score 120-105 = total 225 → LOSS. pnl_units = -stake."""
    db_path, conn = _build_db(tmp_path)
    bet_id = _insert_pick(conn, "Lakers", "Celtics", "Under", odds=1.91, stake=5.0, line=215.5)
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
