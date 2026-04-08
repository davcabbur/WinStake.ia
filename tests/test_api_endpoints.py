import pytest
import os
import tempfile
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from src.database import Database
from tests.test_database import _make_analysis

client = TestClient(app)

@pytest.fixture
def mock_db():
    """Crea una bd temporal para pruebas."""
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    db = Database(db_path=path)
    yield db
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        pass


@pytest.fixture(autouse=True)
def mock_auth():
    """Bypassea la key para poder testear los endpoints puros."""
    with patch("app.core.api_key._DASHBOARD_API_KEY", "test_key"):
        yield


def get_headers():
    return {"X-API-Key": "test_key"}


def test_get_stats_empty(mock_db):
    with patch("app.api_v1.endpoints.dashboard._get_db", return_value=mock_db):
        response = client.get("/api/dashboard/stats", headers=get_headers())
        assert response.status_code == 200
        data = response.json()
        assert data["total_bets"] == 0
        assert data["win_rate"] == 0
        assert data["total_profit"] == 0.0


def test_get_stats_with_data(mock_db):
    mock_db.save_analysis(_make_analysis())
    # Falsificamos un resultado ganador usando una query directa para recuperar ids
    with mock_db._get_conn() as conn:
        vb_id = conn.execute("SELECT id FROM value_bets").fetchone()[0]
    mock_db.record_result(vb_id, home_goals=2, away_goals=1) # Acierto (Local @ 1.85)
    
    with patch("app.api_v1.endpoints.dashboard._get_db", return_value=mock_db):
        response = client.get("/api/dashboard/stats", headers=get_headers())
        assert response.status_code == 200
        data = response.json()
        assert data["total_bets"] == 1
        assert data["win_rate"] == 100.0
        assert data["total_profit"] > 0


def test_get_history(mock_db):
    mock_db.save_analysis(_make_analysis(home="Atleti", away="Real Madrid"))
    
    with patch("app.api_v1.endpoints.dashboard._get_db", return_value=mock_db):
        response = client.get("/api/dashboard/history?limit=10", headers=get_headers())
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["home_team"] == "Atleti"


def test_get_chart_data(mock_db):
    mock_db.save_analysis(_make_analysis())
    with mock_db._get_conn() as conn:
        vb_id = conn.execute("SELECT id FROM value_bets").fetchone()[0]
    mock_db.record_result(vb_id, home_goals=2, away_goals=1)
    
    with patch("app.api_v1.endpoints.dashboard._get_db", return_value=mock_db):
        response = client.get("/api/dashboard/chart-data", headers=get_headers())
        assert response.status_code == 200
        data = response.json()
        assert "dates" in data
        assert "cumulative_profit" in data
        assert len(data["cumulative_profit"]) == 1


@patch("app.api_v1.endpoints.analysis.OddsClient")
@patch("app.api_v1.endpoints.analysis.FootballClient")
def test_run_analysis_engine(mock_football_class, mock_odds_class):
    """Prueba el disparador principal de la API que arranca el pipeline de Machine Learning."""
    mock_odds = mock_odds_class.return_value
    mock_odds.get_upcoming_odds.return_value = [
        {"home_team": "Team A", "away_team": "Team B", "avg_odds": {"home": 2.0}, "commence_time": ""}
    ]

    mock_football = mock_football_class.return_value
    mock_football.get_standings.return_value = []
    mock_football.find_team_in_standings.return_value = None
    mock_football.get_h2h.return_value = []
    
    # We patch Analyzer inside the endpoint to bypass ML processing
    with patch("app.api_v1.endpoints.analysis.Analyzer") as mock_analyzer_class:
        mock_analyzer = mock_analyzer_class.return_value
        
        # Simulamos que encuentra un value bet
        from src.analyzer import MatchAnalysis, EVResult, KellyResult
        mock_analysis = MagicMock()
        mock_analysis.ev_results = [
            MagicMock(is_value=True, selection="Local", odds=2.0, ev_percent=5.0, probability=0.525)
        ]
        mock_analyzer.analyze_match.return_value = mock_analysis
        mock_analyzer._kelly_criterion.return_value = MagicMock(kelly_half=2.5, stake_units=2.5)
        mock_analyzer._classify_confidence.return_value = "Media"
        
        response = client.get("/api/v1/analysis/", headers=get_headers())
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["total_analyzed"] == 1
        assert len(data["value_bets"]) == 1
        assert data["value_bets"][0]["selection"] == "Local"
