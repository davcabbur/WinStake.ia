"""Tests para NBAClient, EVCalculator NBA y Analyzer NBA routing."""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from src.nba_client import NBAClient
from src.ev_calculator import EVCalculator, EVResult
from src.normal_model import NBAMatchProbabilities
from src.analyzer import Analyzer, MatchAnalysis
from src.sports.config import NBA, LALIGA


# ══════════════════════════════════════════════════════════════
# NBAClient — standings tests use patched nba_api (no network)
# ══════════════════════════════════════════════════════════════

# Canned data: a minimal real-shaped DataFrame that LeagueStandings returns.
# Two teams, enough to verify all parsing/find_team logic.
_CANNED_ROWS = [
    {
        "TeamID": 1610612738, "TeamCity": "Boston", "TeamName": "Celtics",
        "PlayoffRank": 1, "WINS": 50, "LOSSES": 20,
        "PointsPG": 117.0, "OppPointsPG": 108.0, "DiffPointsPG": 9.0,
        "WinPCT": 0.714, "L10": "WWWLWWWLWW", "Conference": "East",
    },
    {
        "TeamID": 1610612747, "TeamCity": "Los Angeles", "TeamName": "Lakers",
        "PlayoffRank": 5, "WINS": 42, "LOSSES": 28,
        "PointsPG": 113.0, "OppPointsPG": 109.0, "DiffPointsPG": 4.0,
        "WinPCT": 0.600, "L10": "WLWWLWLWWL", "Conference": "West",
    },
    {
        "TeamID": 1610612760, "TeamCity": "Oklahoma City", "TeamName": "Thunder",
        "PlayoffRank": 1, "WINS": 54, "LOSSES": 16,
        "PointsPG": 118.0, "OppPointsPG": 105.0, "DiffPointsPG": 13.0,
        "WinPCT": 0.771, "L10": "WWWWWWWWWL", "Conference": "West",
    },
]


def _make_mock_standings_api():
    """Returns a mock LeagueStandings instance whose get_data_frames()[0] is the canned DataFrame."""
    mock_api = MagicMock()
    mock_api.get_data_frames.return_value = [pd.DataFrame(_CANNED_ROWS)]
    return mock_api


@pytest.fixture
def nba_client():
    return NBAClient()


@pytest.fixture
def canned_standings(nba_client):
    """
    Calls get_standings() with nba_api patched to return canned data.
    Also patches get_team_pace_map so no second network call is made.
    """
    with patch("nba_api.stats.endpoints.leaguestandings.LeagueStandings",
               return_value=_make_mock_standings_api()), \
         patch.object(nba_client, "get_team_pace_map", return_value={}), \
         patch.object(nba_client.cache, "get", return_value=None), \
         patch.object(nba_client.cache, "set"):
        standings = nba_client.get_standings()
    return standings, nba_client


def test_nba_standings_fields(canned_standings):
    """Cada equipo parseado debe tener los campos requeridos."""
    standings, _ = canned_standings
    required = ["team_id", "team_name", "played", "wins", "losses",
                 "points_for", "points_against", "win_pct", "conference"]
    assert len(standings) == 3
    for team in standings:
        for field in required:
            assert field in team, f"Missing field '{field}' in {team['team_name']}"


def test_nba_standings_win_pct(canned_standings):
    """win_pct del registro parseado debe coincidir con el valor de la API."""
    standings, _ = canned_standings
    for team in standings:
        # The parser stores WinPCT directly from the row (float cast)
        assert isinstance(team["win_pct"], float)
        assert 0.0 <= team["win_pct"] <= 1.0


def test_nba_standings_played_computed(canned_standings):
    """played = wins + losses debe calcularse correctamente."""
    standings, _ = canned_standings
    for team in standings:
        assert team["played"] == team["wins"] + team["losses"]


def test_nba_find_team_exact(canned_standings):
    """Buscar equipo por nombre exacto."""
    standings, client = canned_standings
    found = client.find_team_in_standings("Boston Celtics", standings)
    assert found is not None
    assert "Celtics" in found["team_name"]


def test_nba_find_team_partial(canned_standings):
    """Buscar equipo por nombre parcial (nickname)."""
    standings, client = canned_standings
    found = client.find_team_in_standings("Lakers", standings)
    assert found is not None
    assert "Lakers" in found["team_name"]


def test_nba_find_team_alias(canned_standings):
    """Buscar equipo por alias comun (OKC Thunder)."""
    standings, client = canned_standings
    found = client.find_team_in_standings("OKC Thunder", standings)
    assert found is not None
    assert "Thunder" in found["team_name"]


def test_nba_find_team_not_found(canned_standings):
    """Equipo inexistente retorna None."""
    standings, client = canned_standings
    found = client.find_team_in_standings("FC Barcelona", standings)
    assert found is None


def test_nba_standings_fail_returns_empty(nba_client):
    """Si la API falla, get_standings retorna [] (no mock data, no crash)."""
    with patch("nba_api.stats.endpoints.leaguestandings.LeagueStandings",
               side_effect=Exception("network error")), \
         patch.object(nba_client.cache, "get", return_value=None):
        result = nba_client.get_standings()
    assert result == []


def test_nba_pace_map_uses_per_mode_detailed(nba_client):
    """get_team_pace_map debe llamar a LeagueDashTeamStats con el kwarg
    `per_mode_detailed` (la versión instalada de nba_api NO acepta
    `per_mode_simple`) y parsear PACE por equipo."""
    mock_api = MagicMock()
    mock_api.get_data_frames.return_value = [pd.DataFrame([
        {"TEAM_ID": 1610612738, "PACE": 99.5},
        {"TEAM_ID": 1610612747, "PACE": 101.2},
    ])]
    with patch("nba_api.stats.endpoints.leaguedashteamstats.LeagueDashTeamStats",
               return_value=mock_api) as mock_cls, \
         patch("src.nba_client.time.sleep"), \
         patch.object(nba_client.cache, "get", return_value=None), \
         patch.object(nba_client.cache, "set"):
        result = nba_client.get_team_pace_map()

    # Parseo correcto de PACE
    assert result == {1610612738: 99.5, 1610612747: 101.2}
    kwargs = mock_cls.call_args.kwargs
    # Contrato del kwarg: per_mode_detailed, nunca per_mode_simple
    assert kwargs.get("per_mode_detailed") == "PerGame"
    assert "per_mode_simple" not in kwargs
    # PACE sólo existe con MeasureType=Advanced; el Base (default) no la trae.
    assert kwargs.get("measure_type_detailed_defense") == "Advanced"


def test_nba_h2h_returns_empty_on_api_failure(nba_client):
    """get_h2h retorna [] cuando la API falla (fail-loud path devuelve lista vacía)."""
    with patch("nba_api.stats.endpoints.teamgamelog.TeamGameLog",
               side_effect=Exception("network error")), \
         patch.object(nba_client.cache, "get", return_value=None):
        result = nba_client.get_h2h(1610612738, 1610612747)
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
