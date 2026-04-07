"""Tests para NBAClient, EVCalculator NBA y Analyzer NBA routing."""

import pytest
from src.nba_client import NBAClient
from src.ev_calculator import EVCalculator, EVResult
from src.normal_model import NBAMatchProbabilities
from src.analyzer import Analyzer, MatchAnalysis
from src.sports.config import NBA, LALIGA


# ══════════════════════════════════════════════════════════════
# NBAClient
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def nba_client():
    client = NBAClient()
    client._mock_mode = True
    return client


def test_nba_mock_standings_30_teams(nba_client):
    """Mock standings deben tener 30 equipos NBA."""
    standings = nba_client.get_standings()
    assert len(standings) == 30


def test_nba_standings_fields(nba_client):
    """Cada equipo debe tener los campos requeridos."""
    standings = nba_client.get_standings()
    required = ["team_id", "team_name", "played", "wins", "losses",
                 "points_for", "points_against", "win_pct", "conference"]
    for team in standings:
        for field in required:
            assert field in team, f"Missing field '{field}' in {team['team_name']}"


def test_nba_standings_win_pct(nba_client):
    """win_pct debe ser wins/played."""
    standings = nba_client.get_standings()
    for team in standings:
        expected = round(team["wins"] / team["played"], 3)
        assert team["win_pct"] == expected


def test_nba_find_team_exact(nba_client):
    """Buscar equipo por nombre exacto."""
    standings = nba_client.get_standings()
    found = nba_client.find_team_in_standings("Boston Celtics", standings)
    assert found is not None
    assert "Celtics" in found["team_name"]


def test_nba_find_team_partial(nba_client):
    """Buscar equipo por nombre parcial."""
    standings = nba_client.get_standings()
    found = nba_client.find_team_in_standings("Lakers", standings)
    assert found is not None
    assert "Lakers" in found["team_name"]


def test_nba_find_team_alias(nba_client):
    """Buscar equipo por alias comun."""
    standings = nba_client.get_standings()
    found = nba_client.find_team_in_standings("OKC Thunder", standings)
    assert found is not None
    assert "Thunder" in found["team_name"]


def test_nba_find_team_not_found(nba_client):
    """Equipo inexistente retorna None."""
    standings = nba_client.get_standings()
    found = nba_client.find_team_in_standings("FC Barcelona", standings)
    assert found is None


def test_nba_h2h_mock_returns_empty(nba_client):
    """En mock mode, H2H retorna lista vacia."""
    result = nba_client.get_h2h(1, 2)
    assert result == []


def test_nba_top_scorers_returns_empty(nba_client):
    """NBA client no usa goleadores individuales."""
    assert nba_client.get_top_scorers() == []


# ══════════════════════════════════════════════════════════════
# EVCalculator NBA
# ══════════════════════════════════════════════════════════════

@pytest.fixture
def ev_calc():
    calc = EVCalculator()
    calc.min_ev = 0.03
    return calc


def test_ev_nba_moneyline(ev_calc):
    """EV para moneyline NBA."""
    probs = NBAMatchProbabilities(
        home_win=0.65, away_win=0.35,
        home_cover_prob=0.55, away_cover_prob=0.45,
        over_total=0.52, under_total=0.48,
    )
    odds = {"home": 1.55, "away": 2.50}
    results = ev_calc.calculate_ev_nba(probs, odds)

    home = next(r for r in results if r.selection == "Home")
    assert home.probability == 0.65
    # EV = 0.65 * 1.55 - 1 = 0.0075
    assert abs(home.ev - 0.0075) < 0.01


def test_ev_nba_spread(ev_calc):
    """EV para spread NBA."""
    probs = NBAMatchProbabilities(
        home_win=0.65, away_win=0.35,
        home_cover_prob=0.58, away_cover_prob=0.42,
        over_total=0.52, under_total=0.48,
    )
    odds = {"spread_home": 1.91, "spread_away": 1.91}
    results = ev_calc.calculate_ev_nba(probs, odds)

    spread_home = next(r for r in results if r.selection == "Spread Home")
    # EV = 0.58 * 1.91 - 1 = 0.1078
    assert spread_home.ev > 0
    assert spread_home.is_value is True


def test_ev_nba_totals(ev_calc):
    """EV para totals NBA."""
    probs = NBAMatchProbabilities(
        home_win=0.50, away_win=0.50,
        home_cover_prob=0.50, away_cover_prob=0.50,
        over_total=0.55, under_total=0.45,
    )
    odds = {"over": 1.90, "under": 1.90}
    results = ev_calc.calculate_ev_nba(probs, odds)

    over = next(r for r in results if r.selection == "Over")
    # EV = 0.55 * 1.90 - 1 = 0.045
    assert over.ev > 0.03
    assert over.is_value is True


def test_ev_nba_skips_missing_odds(ev_calc):
    """Mercados sin cuota se omiten."""
    probs = NBAMatchProbabilities(
        home_win=0.60, away_win=0.40,
        home_cover_prob=0.55, away_cover_prob=0.45,
        over_total=0.50, under_total=0.50,
    )
    odds = {"home": 1.60}  # Solo moneyline home
    results = ev_calc.calculate_ev_nba(probs, odds)

    selections = [r.selection for r in results]
    assert "Home" in selections
    assert "Spread Home" not in selections
    assert "Over" not in selections


def test_ev_nba_rejects_odds_below_one(ev_calc):
    """Cuotas <= 1.0 se ignoran."""
    probs = NBAMatchProbabilities(
        home_win=0.90, away_win=0.10,
        home_cover_prob=0.80, away_cover_prob=0.20,
        over_total=0.50, under_total=0.50,
    )
    odds = {"home": 1.0, "away": 5.0}
    results = ev_calc.calculate_ev_nba(probs, odds)

    selections = [r.selection for r in results]
    assert "Home" not in selections
    assert "Away" in selections


# ══════════════════════════════════════════════════════════════
# Correlation Detection NBA
# ══════════════════════════════════════════════════════════════

def test_nba_correlation_ml_spread():
    """Home ML + Spread Home son redundantes."""
    results = [
        EVResult(selection="Home", ev=0.10, is_value=True),
        EVResult(selection="Spread Home", ev=0.08, is_value=True),
    ]
    warnings = EVCalculator.detect_correlated_bets_nba(results)
    assert len(warnings) == 1
    assert "redundantes" in warnings[0]


def test_nba_correlation_ml_over():
    """ML + Over parcialmente correlacionados."""
    results = [
        EVResult(selection="Home", ev=0.10, is_value=True),
        EVResult(selection="Over", ev=0.05, is_value=True),
    ]
    warnings = EVCalculator.detect_correlated_bets_nba(results)
    assert len(warnings) == 1
    assert "parcial" in warnings[0]


def test_nba_no_correlation_single_bet():
    """Una sola bet no tiene correlacion."""
    results = [
        EVResult(selection="Home", ev=0.10, is_value=True),
        EVResult(selection="Under", ev=-0.05, is_value=False),
    ]
    warnings = EVCalculator.detect_correlated_bets_nba(results)
    assert warnings == []


# ══════════════════════════════════════════════════════════════
# Analyzer Routing
# ══════════════════════════════════════════════════════════════

def test_analyzer_routes_to_nba():
    """Con sport_config NBA, analyze_match usa modelo Normal."""
    analyzer = Analyzer(sport_config=NBA)
    odds = {"home": 1.55, "away": 2.50, "spread_home": 1.91, "spread_away": 1.91,
            "spread_line": -5.5, "over": 1.90, "under": 1.90, "total_line": 224.5}

    analysis = analyzer.analyze_match("Boston Celtics", "New York Knicks", odds)

    assert analysis.sport == "nba"
    assert isinstance(analysis.probabilities, NBAMatchProbabilities)
    assert analysis.probabilities.draw == 0.0
    assert analysis.probabilities.home_score > 0
    assert len(analysis.spread_lines) > 0
    assert len(analysis.total_lines) > 0


def test_analyzer_routes_to_football():
    """Con sport_config La Liga, analyze_match usa modelo Poisson."""
    analyzer = Analyzer(sport_config=LALIGA)
    odds = {"home": 1.85, "draw": 3.40, "away": 4.20}

    analysis = analyzer.analyze_match("Real Madrid", "Barcelona", odds)

    assert analysis.sport == "laliga"
    assert analysis.probabilities.draw > 0  # Futbol tiene empate
    assert len(analysis.correct_scores) > 0
    assert analysis.asian_handicap.get("lines")


def test_analyzer_nba_with_stats():
    """Analisis NBA con stats de equipos."""
    analyzer = Analyzer(sport_config=NBA)
    odds = {"home": 1.65, "away": 2.25, "spread_home": 1.91, "spread_away": 1.91,
            "spread_line": -4.5, "over": 1.87, "under": 1.93, "total_line": 222.5}
    home_stats = {
        "played": 70, "points_for": 8120, "points_against": 7490,
        "win_pct": 0.743, "pace": 98.5, "std_dev_factor": 1.0,
    }
    away_stats = {
        "played": 70, "points_for": 8050, "points_against": 7700,
        "win_pct": 0.629, "pace": 101.5, "std_dev_factor": 1.0,
    }

    analysis = analyzer.analyze_match(
        "Cleveland Cavaliers", "Milwaukee Bucks", odds,
        home_stats=home_stats, away_stats=away_stats,
    )

    assert analysis.probabilities.home_score > 0
    assert analysis.probabilities.away_score > 0
    assert len(analysis.ev_results) > 0
    assert len(analysis.insights) > 0


def test_analyzer_nba_no_stats():
    """Analisis NBA sin stats (solo cuotas)."""
    analyzer = Analyzer(sport_config=NBA)
    odds = {"home": 1.80, "away": 2.00}

    analysis = analyzer.analyze_match("Team A", "Team B", odds)

    assert analysis.probabilities.home_win > 0
    assert analysis.probabilities.away_win > 0
    assert analysis.probabilities.home_score > 0


def test_analyzer_nba_calibrate():
    """Calibracion NBA no debe fallar."""
    analyzer = Analyzer(sport_config=NBA)
    standings = [
        {"points_for": 8000, "played": 70},
        {"points_for": 7500, "played": 70},
    ]
    analyzer.calibrate_from_standings(standings)
    # No debe lanzar excepcion


def test_analyzer_default_is_football():
    """Sin sport_config, default es futbol."""
    analyzer = Analyzer()
    assert analyzer.sport_type == "football"
    assert analyzer.sport_key == "laliga"
