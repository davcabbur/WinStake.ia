import pytest
from src.analyzer import Analyzer, MatchAnalysis, EVResult

@pytest.fixture
def analyzer():
    a = Analyzer()
    # Mockear un min_ev pequeño para facilitar asserts
    a.min_ev = 2.0
    return a

def test_poisson_probabilities(analyzer):
    """Prueba que el motor devuelve una suma de probalidades cercana a 1."""
    probs = analyzer._poisson_probabilities(1.5, 1.2)
    total = probs.home_win + probs.draw + probs.away_win
    
    assert 0.99 <= total <= 1.01
    assert probs.home_win > probs.away_win # 1.5 > 1.2

def test_calculate_ev(analyzer):
    """Prueba el cálculo de valor esperado basico."""
    # Probabilidad asimétrica irreal para provocar value
    class MockProbs:
        home_win = 0.8
        draw = 0.1
        away_win = 0.1
        btts_yes = 0.5
        btts_no = 0.5
        over_25 = 0.6
        under_25 = 0.4
        
    odds = {"home": 2.0, "draw": 3.5, "away": 4.0}
    
    ev_results = analyzer._calculate_ev(MockProbs(), odds)
    
    # 0.8 * 2.0 = 1.6 -> EV de +60%
    home_bet = next(x for x in ev_results if x.selection == "Local")
    assert home_bet.is_value is True
    assert home_bet.ev_percent > 50.0

def test_kelly_criterion(analyzer):
    """Comprueba el cálculo de stake Kelly."""
    kelly = analyzer._kelly_criterion(probability=0.55, odds=2.0)
    # Edge = (0.55 * 2) - 1 = 0.1
    # Fraction = Edge / (2 - 1) = 0.1 (10%)
    
    # Tolerancia decimal
    assert 9.9 <= kelly.kelly_full <= 10.1
    assert 4.9 <= kelly.kelly_half <= 5.1
