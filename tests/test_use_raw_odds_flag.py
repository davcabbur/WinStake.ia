"""
Tests del feature flag USE_RAW_ODDS sobre el helper resolve_odds_source.

Garantizan que:
- Por defecto (USE_RAW_ODDS=0) el motor lee avg_odds y bookmaker_meta=None
  (comportamiento histórico — sin alterar producción).
- Con USE_RAW_ODDS=1 lee chosen_book_odds y chosen_book_meta del match,
  habilitando el snapshot de cuota cruda para paper trading.
"""

import pytest

import config
from src.odds_client import resolve_odds_source


@pytest.fixture
def match_dict():
    """Match con los 3 dicts emitidos por _parse_odds, valores distintos."""
    return {
        "id": "test_match",
        "home_team": "Home",
        "away_team": "Away",
        "avg_odds": {
            "home": 1.83,                # trimmed mean
            "draw": 3.45,
            "away": 4.10,
        },
        "chosen_book_odds": {
            "home": 1.85,                # cuota cruda de Bet365
            "draw": 3.40,
            "away": 4.20,
        },
        "chosen_book_meta": {
            "home": "bet365",
            "draw": "bet365",
            "away": "bet365",
        },
        "bet365_odds": {"available": True},
    }


def test_use_raw_odds_off_uses_avg(monkeypatch, match_dict):
    """USE_RAW_ODDS=False → odds = avg_odds, bookmaker_meta = None."""
    monkeypatch.setattr(config, "USE_RAW_ODDS", False)

    odds, meta = resolve_odds_source(match_dict)

    assert odds is match_dict["avg_odds"]
    assert odds["home"] == 1.83          # trimmed mean, no la cruda
    assert meta is None                  # convención legacy resolverá en save_analysis


def test_use_raw_odds_on_uses_chosen(monkeypatch, match_dict):
    """USE_RAW_ODDS=True → odds = chosen_book_odds, meta = chosen_book_meta."""
    monkeypatch.setattr(config, "USE_RAW_ODDS", True)

    odds, meta = resolve_odds_source(match_dict)

    assert odds is match_dict["chosen_book_odds"]
    assert odds["home"] == 1.85          # cuota cruda de Bet365
    assert meta is match_dict["chosen_book_meta"]
    assert meta["home"] == "bet365"
