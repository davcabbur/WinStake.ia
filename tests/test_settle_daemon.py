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
    with patch.object(settle_daemon, "verify_results", return_value={"verified": 3}) as m_la, \
         patch.object(settle_daemon, "run_backtesting_check", return_value={"resolved": 2}) as m_nba:
        result = settle_daemon.settle_all()

    m_la.assert_called_once()
    m_nba.assert_called_once()
    assert result == {"laliga": {"verified": 3}, "nba": {"resolved": 2}}


def test_settle_all_isolates_laliga_failure():
    with patch.object(settle_daemon, "verify_results", side_effect=RuntimeError("API down")), \
         patch.object(settle_daemon, "run_backtesting_check", return_value={"resolved": 1}) as m_nba:
        result = settle_daemon.settle_all()

    m_nba.assert_called_once()
    assert "error" in result["laliga"]
    assert result["nba"] == {"resolved": 1}


def test_settle_all_isolates_nba_failure():
    with patch.object(settle_daemon, "verify_results", return_value={"verified": 0}) as m_la, \
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
