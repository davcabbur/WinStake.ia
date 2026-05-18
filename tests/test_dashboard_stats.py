"""Tests para GET /api/dashboard/stats."""
import sqlite3
import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)

# DDL mínimo: solo las columnas que usa el endpoint
_SCHEMA = """
CREATE TABLE IF NOT EXISTS value_bets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sport       TEXT    NOT NULL DEFAULT 'nba',
    is_paper    INTEGER NOT NULL DEFAULT 1,
    result      TEXT,
    stake_units REAL,
    pnl_units   REAL
);
"""


@pytest.fixture()
def db(tmp_path, monkeypatch):
    """BD SQLite temporal con schema mínimo; auth desactivada."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("src.api.routes.DB_PATH", db_path)
    # Si DASHBOARD_API_KEY está configurada, auth bloquea los tests.
    # El guard en src/api/auth.py permite acceso libre cuando expected == "".
    monkeypatch.setattr("config.DASHBOARD_API_KEY", "")
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    return db_path


def _insert(db_path: str, rows: list[tuple]) -> None:
    """Inserta filas (sport, is_paper, result, stake_units, pnl_units)."""
    conn = sqlite3.connect(db_path)
    conn.executemany(
        "INSERT INTO value_bets (sport, is_paper, result, stake_units, pnl_units) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()


# ── Test 1 ────────────────────────────────────────────────────────────────────

def test_dashboard_stats_returns_correct_roi(db):
    """ROI = profit / staked — 2 WIN + 1 LOSS, stake=10 cada pick."""
    _insert(db, [
        ("nba", 1, "WIN",  10.0,  10.0),   # pnl = (2.0-1)*10
        ("nba", 1, "WIN",  10.0,  10.0),
        ("nba", 1, "LOSS", 10.0, -10.0),
    ])
    resp = client.get("/api/dashboard/stats?sport=nba")
    assert resp.status_code == 200
    data = resp.json()

    assert data["sport"] == "nba"
    assert data["total_bets"] == 3
    assert data["won_bets"] == 2
    assert data["win_rate"] == pytest.approx(66.67, abs=0.01)
    assert data["total_staked"] == pytest.approx(30.0)
    assert data["total_profit"] == pytest.approx(10.0)
    assert data["roi_pct"] == pytest.approx(33.33, abs=0.01)


# ── Test 2 ────────────────────────────────────────────────────────────────────

def test_dashboard_stats_filters_by_sport(db):
    """?sport= filtra correctamente; LaLiga y NBA no se mezclan."""
    _insert(db, [
        ("nba",    1, "WIN",  5.0,  4.0),
        ("nba",    1, "LOSS", 5.0, -5.0),
        ("laliga", 1, "WIN",  3.0,  2.1),
        ("laliga", 1, "WIN",  3.0,  2.1),
    ])

    resp_nba = client.get("/api/dashboard/stats?sport=nba")
    assert resp_nba.status_code == 200
    assert resp_nba.json()["total_bets"] == 2
    assert resp_nba.json()["sport"] == "nba"

    resp_ll = client.get("/api/dashboard/stats?sport=laliga")
    assert resp_ll.status_code == 200
    assert resp_ll.json()["total_bets"] == 2
    assert resp_ll.json()["sport"] == "laliga"


# ── Test 3 ────────────────────────────────────────────────────────────────────

def test_dashboard_stats_handles_empty_db(db):
    """BD vacía → todos los campos en 0, sin errores, sin division-by-zero."""
    resp = client.get("/api/dashboard/stats?sport=nba")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_bets"] == 0
    assert data["won_bets"] == 0
    assert data["win_rate"] == 0.0
    assert data["total_staked"] == 0.0
    assert data["total_profit"] == 0.0
    assert data["roi_pct"] == 0.0
