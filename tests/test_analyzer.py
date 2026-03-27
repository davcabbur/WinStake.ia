"""
Tests para el motor de análisis de WinStake.ia.
"""

import sys
import os

# Añadir raíz del proyecto al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analyzer import Analyzer, MatchProbabilities, odds_to_implied_probability, remove_overround


def test_poisson_probabilities_sum_to_1():
    """Las probabilidades 1X2 deben sumar 100%."""
    analyzer = Analyzer()
    probs = analyzer._poisson_probabilities(1.5, 1.0)

    total = probs.home_win + probs.draw + probs.away_win
    assert abs(total - 1.0) < 0.01, f"Probabilidades 1X2 suman {total}, deberían sumar 1.0"
    print(f"✅ test_poisson_probabilities_sum_to_1: {probs.home_win:.3f} + {probs.draw:.3f} + {probs.away_win:.3f} = {total:.4f}")


def test_poisson_home_advantage():
    """Con lambda_home > lambda_away, la victoria local debe ser más probable."""
    analyzer = Analyzer()
    probs = analyzer._poisson_probabilities(2.0, 0.8)

    assert probs.home_win > probs.away_win, "Local debería ser favorito con λ mayor"
    assert probs.home_win > probs.draw, "Local debería ser el resultado más probable"
    print(f"✅ test_poisson_home_advantage: Local {probs.home_win:.3f} > Visitante {probs.away_win:.3f}")


def test_poisson_symmetric():
    """Con lambdas iguales, empate debería ser significativo."""
    analyzer = Analyzer()
    probs = analyzer._poisson_probabilities(1.3, 1.3)

    # Con lambdas iguales, local y visitante deberían ser similares
    diff = abs(probs.home_win - probs.away_win)
    assert diff < 0.01, f"Con λ iguales, diff debería ser ~0, es {diff}"
    print(f"✅ test_poisson_symmetric: Local {probs.home_win:.3f} ≈ Visitante {probs.away_win:.3f}")


def test_ev_positive():
    """Prob 50%, cuota 2.20 → EV = +10%."""
    analyzer = Analyzer()
    probs = MatchProbabilities(home_win=0.50, draw=0.25, away_win=0.25)
    odds = {"home": 2.20, "draw": 3.20, "away": 4.00}

    results = analyzer._calculate_ev(probs, odds)
    home_ev = next(r for r in results if r.selection == "Local")

    expected_ev = (0.50 * 2.20) - 1.0  # = 0.10
    assert abs(home_ev.ev - expected_ev) < 0.001, f"EV esperado {expected_ev}, obtenido {home_ev.ev}"
    assert home_ev.is_value, "Debería ser value bet"
    print(f"✅ test_ev_positive: EV = {home_ev.ev_percent:+.1f}% (esperado: +10.0%)")


def test_ev_negative():
    """Prob 30%, cuota 2.50 → EV = -25% → NO es value."""
    analyzer = Analyzer()
    probs = MatchProbabilities(home_win=0.30, draw=0.35, away_win=0.35)
    odds = {"home": 2.50, "draw": 3.00, "away": 3.00}

    results = analyzer._calculate_ev(probs, odds)
    home_ev = next(r for r in results if r.selection == "Local")

    assert home_ev.ev < 0, f"EV debería ser negativo, es {home_ev.ev}"
    assert not home_ev.is_value, "NO debería ser value bet"
    print(f"✅ test_ev_negative: EV = {home_ev.ev_percent:+.1f}% → Correctamente descartado")


def test_kelly_criterion():
    """Prob 50%, cuota 2.20 → Kelly = 8.33%."""
    analyzer = Analyzer()
    kelly = analyzer._kelly_criterion(0.50, 2.20)

    expected_kelly = ((0.50 * 2.20) - 1) / (2.20 - 1)  # = 0.0833
    assert abs(kelly.kelly_full - expected_kelly * 100) < 0.1, \
        f"Kelly esperado {expected_kelly*100:.2f}%, obtenido {kelly.kelly_full:.2f}%"
    assert abs(kelly.kelly_half - expected_kelly * 50) < 0.1
    print(f"✅ test_kelly_criterion: Full {kelly.kelly_full:.2f}% | Half {kelly.kelly_half:.2f}% | Stake {kelly.stake_units}u")


def test_kelly_negative_returns_zero():
    """Si EV es negativo, Kelly debe ser 0."""
    analyzer = Analyzer()
    kelly = analyzer._kelly_criterion(0.20, 2.00)  # EV = (0.2*2)-1 = -0.6

    assert kelly.kelly_full == 0.0, f"Kelly debería ser 0, es {kelly.kelly_full}"
    print(f"✅ test_kelly_negative_returns_zero: Kelly = {kelly.kelly_full}%")


def test_kelly_capped():
    """Kelly no debe exceder el cap (10%)."""
    analyzer = Analyzer()
    kelly = analyzer._kelly_criterion(0.80, 3.00)  # Kelly teórico = 70%

    assert kelly.kelly_full <= 10.0, f"Kelly debería estar limitado a 10%, es {kelly.kelly_full}%"
    print(f"✅ test_kelly_capped: Kelly = {kelly.kelly_full}% (cap: 10%)")


def test_odds_to_implied():
    """Cuota 2.00 → 50% probabilidad implícita."""
    prob = odds_to_implied_probability(2.00)
    assert abs(prob - 0.50) < 0.001
    print(f"✅ test_odds_to_implied: 2.00 → {prob*100}%")


def test_remove_overround():
    """Eliminar margen de la casa."""
    probs = {"home": 0.40, "draw": 0.30, "away": 0.35}  # Total = 1.05 (5% overround)
    adjusted = remove_overround(probs)

    total = sum(adjusted.values())
    assert abs(total - 1.0) < 0.001, f"Ajustado suma {total}, debería ser 1.0"
    print(f"✅ test_remove_overround: Total ajustado = {total:.4f}")


def test_full_match_analysis():
    """Test de integración: análisis completo de un partido."""
    analyzer = Analyzer()

    home_stats = {
        "team_name": "Barcelona", "rank": 1, "points": 77,
        "played": 29, "wins": 24, "draws": 5, "losses": 0,
        "goals_for": 78, "goals_against": 28, "goal_diff": 50,
        "home": {"played": 15, "wins": 14, "draws": 1, "losses": 0, "goals_for": 47, "goals_against": 11},
        "away": {"played": 14, "wins": 10, "draws": 4, "losses": 0, "goals_for": 31, "goals_against": 17},
    }
    away_stats = {
        "team_name": "Real Oviedo", "rank": 20, "points": 21,
        "played": 29, "wins": 4, "draws": 9, "losses": 16,
        "goals_for": 20, "goals_against": 48, "goal_diff": -28,
        "home": {"played": 15, "wins": 3, "draws": 5, "losses": 7, "goals_for": 12, "goals_against": 19},
        "away": {"played": 14, "wins": 1, "draws": 4, "losses": 9, "goals_for": 8, "goals_against": 29},
    }

    odds = {"home": 1.15, "draw": 7.00, "away": 18.00, "over_25": 1.40, "under_25": 3.00}

    analysis = analyzer.analyze_match(
        home_team="Barcelona", away_team="Real Oviedo",
        odds=odds, home_stats=home_stats, away_stats=away_stats,
    )

    assert analysis.probabilities.home_win > 0.60, "Barcelona debería ser favorito claro"
    assert len(analysis.ev_results) > 0, "Debería haber resultados de EV"
    assert len(analysis.insights) > 0, "Debería haber insights"
    print(f"✅ test_full_match_analysis: Barcelona ({analysis.probabilities.home_win*100:.1f}%) "
          f"vs Oviedo ({analysis.probabilities.away_win*100:.1f}%)")
    print(f"   Mejor apuesta: {analysis.recommendation}")
    print(f"   Insights ({len(analysis.insights)}):")
    for ins in analysis.insights[:3]:
        print(f"     • {ins}")


def main():
    """Ejecuta todos los tests."""
    print("=" * 60)
    print("  WinStake.ia — Test Suite")
    print("=" * 60)
    print()

    tests = [
        test_poisson_probabilities_sum_to_1,
        test_poisson_home_advantage,
        test_poisson_symmetric,
        test_ev_positive,
        test_ev_negative,
        test_kelly_criterion,
        test_kelly_negative_returns_zero,
        test_kelly_capped,
        test_odds_to_implied,
        test_remove_overround,
        test_full_match_analysis,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {test.__name__}: ERROR — {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  Resultado: {passed}/{passed + failed} tests pasados")
    if failed:
        print(f"  ❌ {failed} tests fallidos")
    else:
        print("  ✅ Todos los tests pasados")
    print(f"{'=' * 60}")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
