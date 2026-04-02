import pytest
from src.backtester.engine import (
    BacktestEngine, TeamStatsTracker, _check_bet_won, BacktestResult,
)


def _make_matches():
    """Genera una mini-temporada de 20 partidos para tests."""
    teams = ["Team A", "Team B", "Team C", "Team D"]
    matches = []
    scores = [
        (2, 1), (0, 0), (1, 3), (1, 1),
        (3, 0), (2, 2), (0, 1), (1, 0),
        (2, 1), (1, 1), (0, 2), (3, 1),
        (1, 0), (2, 2), (0, 1), (1, 3),
        (2, 0), (1, 1), (3, 2), (0, 0),
    ]

    idx = 0
    for round_num in range(5):
        for i in range(0, 4, 2):
            home = teams[i]
            away = teams[(i + 1 + round_num) % 4]
            hg, ag = scores[idx]
            result = "H" if hg > ag else ("D" if hg == ag else "A")
            matches.append({
                "date": f"2025-0{round_num+1}-01",
                "home_team": home,
                "away_team": away,
                "home_goals": hg,
                "away_goals": ag,
                "result": result,
                "odds": {"home": 1.85, "draw": 3.40, "away": 4.20},
            })
            idx += 1

    return matches


# ── TeamStatsTracker ──────────────────────────────────────

def test_tracker_init():
    tracker = TeamStatsTracker()
    assert tracker.get_stats("Unknown") is None


def test_tracker_update():
    tracker = TeamStatsTracker()
    tracker.update("A", "B", 2, 1)

    stats_a = tracker.get_stats("A")
    assert stats_a is not None
    assert stats_a["played"] == 1
    assert stats_a["goals_for"] == 2
    assert stats_a["goals_against"] == 1

    stats_b = tracker.get_stats("B")
    assert stats_b["goals_for"] == 1


def test_tracker_form():
    tracker = TeamStatsTracker()
    tracker.update("A", "B", 2, 1)  # A wins
    tracker.update("A", "C", 0, 0)  # A draws
    tracker.update("A", "D", 0, 1)  # A loses

    form = tracker.get_form("A")
    assert form == "WDL"


def test_tracker_home_away_split():
    tracker = TeamStatsTracker()
    tracker.update("Home", "Away", 3, 1)

    stats = tracker.get_stats("Home")
    assert stats["home"]["goals_for"] == 3
    assert stats["home"]["played"] == 1
    assert stats["away"]["goals_for"] == 0


# ── Check Bet Won ─────────────────────────────────────────

def test_check_bet_local():
    assert _check_bet_won("Local", 2, 1) is True
    assert _check_bet_won("Local", 1, 2) is False


def test_check_bet_over():
    assert _check_bet_won("Over 2.5", 2, 1) is True
    assert _check_bet_won("Over 2.5", 1, 1) is False


def test_check_bet_under():
    assert _check_bet_won("Under 2.5", 1, 0) is True
    assert _check_bet_won("Under 2.5", 2, 1) is False


def test_check_bet_btts():
    assert _check_bet_won("BTTS Sí", 1, 1) is True
    assert _check_bet_won("BTTS Sí", 1, 0) is False
    assert _check_bet_won("BTTS No", 1, 0) is True


# ── BacktestEngine ────────────────────────────────────────

def test_backtest_runs_without_error():
    """El engine debe ejecutar una temporada sin crashear."""
    matches = _make_matches()
    engine = BacktestEngine(initial_bankroll=100.0, min_matches_before_bet=3)
    result = engine.run_season(matches, min_ev=1.0)

    assert isinstance(result, BacktestResult)
    assert result.initial_bankroll == 100.0
    assert result.final_bankroll > 0


def test_backtest_result_fields():
    """El resultado debe tener todos los campos esperados."""
    matches = _make_matches()
    engine = BacktestEngine(min_matches_before_bet=3)
    result = engine.run_season(matches, min_ev=1.0)

    assert result.total_bets >= 0
    assert result.wins + result.losses == result.total_bets
    assert 0 <= result.win_rate <= 100
    assert result.max_drawdown >= 0
    assert result.longest_losing_streak >= 0
    assert isinstance(result.predictions, list)
    assert isinstance(result.history, list)
    assert isinstance(result.bankroll_curve, list)


def test_backtest_high_min_ev_fewer_bets():
    """Min EV alto debe generar menos apuestas que min EV bajo."""
    matches = _make_matches()

    engine_low = BacktestEngine(min_matches_before_bet=3)
    result_low = engine_low.run_season(matches, min_ev=1.0)

    engine_high = BacktestEngine(min_matches_before_bet=3)
    result_high = engine_high.run_season(matches, min_ev=20.0)

    assert result_high.total_bets <= result_low.total_bets


def test_backtest_predictions_generated():
    """Deben generarse predicciones para calibración."""
    matches = _make_matches()
    engine = BacktestEngine(min_matches_before_bet=3)
    result = engine.run_season(matches, min_ev=1.0)

    assert len(result.predictions) > 0
    pred = result.predictions[0]
    assert "prob_home" in pred
    assert "prob_draw" in pred
    assert "actual_result" in pred


def test_backtest_bankroll_curve():
    """La curva de bankroll debe tener al menos el punto inicial."""
    matches = _make_matches()
    engine = BacktestEngine(min_matches_before_bet=3)
    result = engine.run_season(matches, min_ev=1.0)

    assert len(result.bankroll_curve) >= 1
    assert result.bankroll_curve[0] == 100.0
    assert result.bankroll_curve[-1] == result.final_bankroll
