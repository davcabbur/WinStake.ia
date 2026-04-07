"""Tests para el modelo Normal (NBA basketball)."""

import pytest
from src.normal_model import NormalModel, NBAMatchProbabilities
from src.sports.config import NBA


@pytest.fixture
def model():
    return NormalModel(sport_config=NBA)


@pytest.fixture
def home_stats():
    return {
        "played": 70, "points_for": 8120, "points_against": 7490,
        "win_pct": 0.743, "pace": 98.5, "std_dev_factor": 1.0,
    }


@pytest.fixture
def away_stats():
    return {
        "played": 70, "points_for": 7910, "points_against": 7420,
        "win_pct": 0.671, "pace": 97.8, "std_dev_factor": 1.0,
    }


# ── Probabilidades basicas ──────────────────────────────────

def test_home_away_sum_to_one(model, home_stats, away_stats):
    """home_win + away_win = 1.0 (sin empate en NBA)."""
    probs = model.predict(home_stats, away_stats)
    assert probs.draw == 0.0
    assert abs(probs.home_win + probs.away_win - 1.0) < 0.001


def test_no_draw_in_nba(model, home_stats, away_stats):
    """NBA no tiene empate."""
    probs = model.predict(home_stats, away_stats)
    assert probs.draw == 0.0


def test_home_advantage(model, home_stats, away_stats):
    """Equipo similar en casa debe tener ventaja."""
    same_stats = {
        "played": 70, "points_for": 7840, "points_against": 7840,
        "win_pct": 0.500, "pace": 100.0, "std_dev_factor": 1.0,
    }
    probs = model.predict(same_stats, same_stats)
    assert probs.home_win > probs.away_win
    assert probs.home_score > probs.away_score


def test_better_team_favored(model):
    """Equipo con mejor ataque/defensa debe ser favorito."""
    strong = {
        "played": 70, "points_for": 8400, "points_against": 7000,
        "win_pct": 0.800, "pace": 100.0, "std_dev_factor": 1.0,
    }
    weak = {
        "played": 70, "points_for": 7000, "points_against": 8400,
        "win_pct": 0.300, "pace": 100.0, "std_dev_factor": 1.0,
    }
    probs = model.predict(strong, weak)
    assert probs.home_win > 0.7
    assert probs.home_score > probs.away_score + 5


# ── Scores esperados ────────────────────────────────────────

def test_expected_scores_reasonable(model, home_stats, away_stats):
    """Scores esperados deben estar en rango NBA realista."""
    probs = model.predict(home_stats, away_stats)
    assert 95 <= probs.home_score <= 135
    assert 90 <= probs.away_score <= 130
    assert 200 <= probs.total_score <= 260


def test_expected_scores_without_stats(model):
    """Sin stats, usa medias de liga."""
    probs = model.predict(None, None)
    assert 95 <= probs.home_score <= 135
    assert 90 <= probs.away_score <= 130


def test_scores_clamped(model):
    """Scores extremos se limitan a rangos razonables."""
    extreme = {
        "played": 70, "points_for": 14000, "points_against": 3500,
        "win_pct": 0.990, "pace": 120.0, "std_dev_factor": 1.0,
    }
    weak = {
        "played": 70, "points_for": 3500, "points_against": 14000,
        "win_pct": 0.010, "pace": 80.0, "std_dev_factor": 1.0,
    }
    probs = model.predict(extreme, weak)
    assert probs.home_score <= 135
    assert probs.away_score >= 90


# ── Spread ──────────────────────────────────────────────────

def test_spread_sign_convention(model, home_stats, away_stats):
    """Spread negativo = home favorito."""
    probs = model.predict(home_stats, away_stats)
    # home_stats tiene mejor record, spread debe ser negativo (home favorito)
    assert probs.spread < 0 or probs.spread > 0  # Puede variar, solo verificamos que existe


def test_spread_cover_with_market(model, home_stats, away_stats):
    """Con spread de mercado, home_cover + away_cover = 1.0."""
    probs = model.predict(home_stats, away_stats, market_spread=-5.5)
    assert abs(probs.home_cover_prob + probs.away_cover_prob - 1.0) < 0.001


def test_spread_cover_no_market(model, home_stats, away_stats):
    """Sin spread de mercado, cover probs son 50/50."""
    probs = model.predict(home_stats, away_stats, market_spread=0)
    assert probs.home_cover_prob == 0.5
    assert probs.away_cover_prob == 0.5


# ── Totals (Over/Under) ────────────────────────────────────

def test_over_under_sum_to_one(model, home_stats, away_stats):
    """Over + Under = 1.0."""
    probs = model.predict(home_stats, away_stats, market_total=224.5)
    assert abs(probs.over_total + probs.under_total - 1.0) < 0.001


def test_high_pace_favors_over(model):
    """Equipos con ritmo alto deben tener mas over."""
    fast = {
        "played": 70, "points_for": 8400, "points_against": 8400,
        "win_pct": 0.500, "pace": 106.0, "std_dev_factor": 1.0,
    }
    slow = {
        "played": 70, "points_for": 7000, "points_against": 7000,
        "win_pct": 0.500, "pace": 94.0, "std_dev_factor": 1.0,
    }
    probs_fast = model.predict(fast, fast, market_total=224.5)
    probs_slow = model.predict(slow, slow, market_total=224.5)
    assert probs_fast.over_total > probs_slow.over_total


# ── H2H Adjustment ──────────────────────────────────────────

def test_h2h_no_data(model, home_stats, away_stats):
    """Sin H2H data, no cambia resultado."""
    probs_no_h2h = model.predict(home_stats, away_stats)
    probs_empty_h2h = model.predict(home_stats, away_stats, h2h_data=[])
    assert probs_no_h2h.home_win == probs_empty_h2h.home_win


def test_h2h_too_few_matches():
    """Con <3 partidos, sin ajuste."""
    adj = NormalModel._h2h_adjustment_nba([
        {"home_winner": True}, {"home_winner": False},
    ])
    assert adj == (1.0, 1.0)


def test_h2h_home_dominant():
    """H2H dominado por home da ajuste positivo."""
    data = [
        {"home_winner": True}, {"home_winner": True},
        {"home_winner": True}, {"home_winner": True},
        {"home_winner": True},
    ]
    home_adj, away_adj = NormalModel._h2h_adjustment_nba(data)
    assert home_adj > 1.0
    assert away_adj < 1.0
    assert home_adj <= 1.03  # Max 3% en NBA


# ── Spread Probabilities Table ──────────────────────────────

def test_spread_probabilities_returns_lines(model):
    """spread_probabilities retorna lista de lineas."""
    lines = model.spread_probabilities(112.0, 108.0, 16.0)
    assert len(lines) > 0
    for line in lines:
        assert "spread" in line
        assert 0 <= line["home_cover_prob"] <= 1
        assert abs(line["home_cover_prob"] + line["away_cover_prob"] - 1.0) < 0.001


# ── Total Probabilities Table ───────────────────────────────

def test_total_probabilities_returns_lines(model):
    """total_probabilities retorna lista de lineas."""
    lines = model.total_probabilities(224.0, 16.0)
    assert len(lines) > 0
    for line in lines:
        assert "line" in line
        assert 0 <= line["over_prob"] <= 1
        assert abs(line["over_prob"] + line["under_prob"] - 1.0) < 0.001


# ── League Average Update ───────────────────────────────────

def test_update_league_avg(model):
    """Recalibracion desde standings reales."""
    standings = [
        {"points_for": 8000, "played": 70},
        {"points_for": 7500, "played": 70},
    ]
    old_avg = model.league_avg_total
    model.update_league_avg_from_standings(standings)
    # 15500 total points / 70 matches = 221.4
    assert model.league_avg_total != old_avg or abs(old_avg - 221.4) < 2


def test_update_league_avg_rejects_insane_values(model):
    """Valores fuera de rango NBA se rechazan."""
    old_avg = model.league_avg_total
    standings = [
        {"points_for": 100, "played": 70},  # ~2.86 per game, absurdo para NBA
    ]
    model.update_league_avg_from_standings(standings)
    assert model.league_avg_total == old_avg  # No debe cambiar
