import os
import pytest
from src.database import Database
from src.analyzer import MatchAnalysis, EVResult

import tempfile

@pytest.fixture
def mock_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    db = Database(db_path=path)
    yield db
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        pass

def test_database_initialization(mock_db):
    """Asegurar que las tablas se crean vacías."""
    cursor = mock_db._get_conn().cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    
    assert "analyses" in tables
    assert "value_bets" in tables
    assert "match_results" in tables

def test_save_and_retrieve_roi(mock_db):
    """Guarda un análisis y comprueba el ROI vacío."""
    roi = mock_db.get_roi_summary()
    assert roi["total_bets"] == 0
    assert roi["wins"] == 0
    assert roi["roi_percent"] == 0.0

    # Guardar uno real
    analysis = MatchAnalysis(
        home_team="Fake Team 1",
        away_team="Fake Team 2",
        commence_time="2025-01-01T20:00:00Z",
        market_odds={"home": 2.0, "draw": 3.0, "away": 3.5}
    )
    analysis.best_bet = EVResult(selection="Local", odds=2.0, probability=0.6, ev_percent=20.0, is_value=True)
    
    # Requeriríamos persistencia mock real, pero al menos probamos el guardado sin fallos
    mock_db.save_analysis(analysis)
    
    # Check si sumó algo (aunque won/loss estarán en null)
    cursor = mock_db._get_conn().cursor()
    cursor.execute("SELECT COUNT(*) FROM value_bets")
    assert cursor.fetchone()[0] == 1
