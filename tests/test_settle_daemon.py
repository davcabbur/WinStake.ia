from unittest.mock import patch

import pytest

from src import settle_daemon


@pytest.mark.parametrize("hour,expected", [
    (10, True),   # arranque ventana
    (15, True),   # mediodía
    (23, True),   # noche
    (1, True),    # madrugada dentro de ventana
    (2, False),   # justo al cerrar ventana
    (5, False),   # mañana muerta
    (9, False),   # justo antes de abrir
])
def test_in_active_window(hour, expected):
    assert settle_daemon.in_active_window(hour) is expected


def test_settle_all_invokes_both_sports():
    with patch.object(settle_daemon.config, "LALIGA_ENABLED", True), \
         patch.object(settle_daemon, "verify_results", return_value={"verified": 3}) as m_la, \
         patch.object(settle_daemon, "run_backtesting_check", return_value={"resolved": 2}) as m_nba:
        result = settle_daemon.settle_all()

    m_la.assert_called_once()
    m_nba.assert_called_once()
    assert result["laliga"] == {"verified": 3}
    assert result["nba"] == {"resolved": 2}


def test_settle_all_skips_laliga_when_disabled():
    with patch.object(settle_daemon.config, "LALIGA_ENABLED", False), \
         patch.object(settle_daemon, "verify_results") as m_la, \
         patch.object(settle_daemon, "run_backtesting_check", return_value={"resolved": 2}) as m_nba:
        result = settle_daemon.settle_all()

    m_la.assert_not_called()
    m_nba.assert_called_once()
    assert result["laliga"] == {"skipped": True}
    assert result["nba"] == {"resolved": 2}


def test_settle_all_isolates_laliga_failure():
    with patch.object(settle_daemon.config, "LALIGA_ENABLED", True), \
         patch.object(settle_daemon, "verify_results", side_effect=RuntimeError("API down")), \
         patch.object(settle_daemon, "run_backtesting_check", return_value={"resolved": 1}) as m_nba:
        result = settle_daemon.settle_all()

    m_nba.assert_called_once()
    assert "error" in result["laliga"]
    assert result["nba"] == {"resolved": 1}


def test_settle_all_isolates_nba_failure():
    with patch.object(settle_daemon.config, "LALIGA_ENABLED", True), \
         patch.object(settle_daemon, "verify_results", return_value={"verified": 0}) as m_la, \
         patch.object(settle_daemon, "run_backtesting_check", side_effect=RuntimeError("nba_api timeout")):
        result = settle_daemon.settle_all()

    m_la.assert_called_once()
    assert result["laliga"] == {"verified": 0}
    assert "error" in result["nba"]


def test_tick_skips_outside_window():
    with patch.object(settle_daemon, "in_active_window", return_value=False), \
         patch.object(settle_daemon, "settle_all") as m_settle:
        settle_daemon.tick()
    m_settle.assert_not_called()


def test_tick_runs_inside_window():
    with patch.object(settle_daemon, "in_active_window", return_value=True), \
         patch.object(settle_daemon, "settle_all") as m_settle:
        settle_daemon.tick()
    m_settle.assert_called_once()


# ── Bloque C: persist_nba_outcomes ───────────────────────────────────────────

def test_persist_nba_outcomes_returns_inserted_count():
    """persist_nba_outcomes llama a fetch + persist y devuelve el campo 'inserted'."""
    with patch.object(settle_daemon, "current_nba_season", return_value="2025-26"), \
         patch.object(settle_daemon, "fetch_nba_season_results", return_value=[{"game_id": "X"}]) as mock_fetch, \
         patch.object(settle_daemon, "_persist_nba_outcomes_to_db", return_value={"inserted": 5, "skipped": 0}) as mock_persist:

        result = settle_daemon.persist_nba_outcomes()

    assert result == 5
    mock_fetch.assert_called_once_with(season="2025-26")
    mock_persist.assert_called_once()


def test_persist_nba_outcomes_returns_zero_on_exception():
    """Si fetch_nba_season_results lanza excepción, devuelve 0 sin propagar."""
    with patch.object(settle_daemon, "fetch_nba_season_results",
                      side_effect=ConnectionError("nba_api timeout")):
        result = settle_daemon.persist_nba_outcomes()

    assert result == 0


def test_settle_includes_nba_outcomes_in_summary():
    """settle_all() debe incluir 'nba_outcomes' en el summary con el valor retornado."""
    with patch.object(settle_daemon.config, "LALIGA_ENABLED", False), \
         patch.object(settle_daemon, "run_backtesting_check", return_value={}), \
         patch.object(settle_daemon, "persist_nba_outcomes", return_value=3):

        result = settle_daemon.settle_all()

    assert "nba_outcomes" in result
    assert result["nba_outcomes"] == 3


def test_settle_logs_outcomes_only_if_positive(caplog):
    """Si persist_nba_outcomes devuelve 0, no se loggea. Si >0, sí."""
    import logging

    base_patches = dict(
        LALIGA_ENABLED=False,
    )

    with patch.object(settle_daemon.config, "LALIGA_ENABLED", False), \
         patch.object(settle_daemon, "run_backtesting_check", return_value={}), \
         patch.object(settle_daemon, "persist_nba_outcomes", return_value=0):
        with caplog.at_level(logging.INFO):
            settle_daemon.settle_all()
    assert "Persistidos" not in caplog.text

    caplog.clear()

    with patch.object(settle_daemon.config, "LALIGA_ENABLED", False), \
         patch.object(settle_daemon, "run_backtesting_check", return_value={}), \
         patch.object(settle_daemon, "persist_nba_outcomes", return_value=5):
        with caplog.at_level(logging.INFO):
            settle_daemon.settle_all()
    assert "Persistidos 5" in caplog.text
