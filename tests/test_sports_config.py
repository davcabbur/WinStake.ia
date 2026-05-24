from unittest.mock import patch
from datetime import datetime
from src.sports.config import current_nba_season


def test_current_nba_season_in_october():
    with patch('src.sports.config.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 10, 15)
        assert current_nba_season() == "2026-27"


def test_current_nba_season_in_may():
    with patch('src.sports.config.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 24)
        assert current_nba_season() == "2025-26"


def test_current_nba_season_in_september():
    with patch('src.sports.config.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 9, 30)
        assert current_nba_season() == "2025-26"


def test_current_nba_season_in_december():
    with patch('src.sports.config.datetime') as mock_dt:
        mock_dt.now.return_value = datetime(2026, 12, 1)
        assert current_nba_season() == "2026-27"
