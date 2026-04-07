import pytest
from src.analyzer import Analyzer, MatchAnalysis, MatchProbabilities, EVResult, KellyResult
from src.ev_calculator import EVCalculator, remove_overround, fair_odds
from src.market_analyzer import form_multiplier, h2h_adjustment, H2H_MIN_MATCHES


@pytest.fixture
def analyzer():
    a = Analyzer()
    a.min_ev = 0.02       # 2% threshold (fracción)
    a._ev_calc.min_ev = 0.02
    return a


# ── Poisson Probabilities ────────────────────────────────

def test_poisson_probabilities_sum_to_one(analyzer):
    """Probabilidades 1X2 deben sumar ~1.0."""
    probs = analyzer._poisson_probabilities(1.5, 1.2)
    total = probs.home_win + probs.draw + probs.away_win
    assert 0.99 <= total <= 1.01


def test_poisson_home_favored_when_higher_lambda(analyzer):
    """Lambda local mayor implica mayor probabilidad local."""
    probs = analyzer._poisson_probabilities(1.5, 1.2)
    assert probs.home_win > probs.away_win


def test_poisson_symmetric_lambdas(analyzer):
    """Lambdas iguales deben dar home_win ~ away_win."""
    probs = analyzer._poisson_probabilities(1.3, 1.3)
    assert abs(probs.home_win - probs.away_win) < 0.01


def test_poisson_over_under_sum(analyzer):
    """Over 2.5 + Under 2.5 deben sumar ~1.0."""
    probs = analyzer._poisson_probabilities(1.5, 1.2)
    assert 0.99 <= (probs.over_25 + probs.under_25) <= 1.01


def test_poisson_btts_sum(analyzer):
    """BTTS Yes + BTTS No deben sumar ~1.0."""
    probs = analyzer._poisson_probabilities(1.5, 1.2)
    assert 0.99 <= (probs.btts_yes + probs.btts_no) <= 1.01


def test_poisson_high_lambda_means_more_goals(analyzer):
    """Lambdas altos deben dar mayor probabilidad de Over 2.5."""
    probs_low = analyzer._poisson_probabilities(0.8, 0.7)
    probs_high = analyzer._poisson_probabilities(2.0, 1.8)
    assert probs_high.over_25 > probs_low.over_25


def test_poisson_very_low_lambda(analyzer):
    """Lambdas muy bajos no deben producir errores."""
    probs = analyzer._poisson_probabilities(0.3, 0.2)
    total = probs.home_win + probs.draw + probs.away_win
    assert 0.99 <= total <= 1.01
    assert probs.draw > 0.3


# ── Expected Value ────────────────────────────────────────

def test_calculate_ev_positive(analyzer):
    """Probabilidad alta + cuota alta = EV positivo."""
    probs = MatchProbabilities(
        home_win=0.8, draw=0.1, away_win=0.1,
        btts_yes=0.5, btts_no=0.5,
        over_25=0.6, under_25=0.4,
    )

    odds = {"home": 2.0, "draw": 3.5, "away": 4.0}
    ev_results = analyzer._calculate_ev(probs, odds)

    home_bet = next(x for x in ev_results if x.selection == "Local")
    assert home_bet.is_value is True
    assert home_bet.ev_percent > 50.0


def test_calculate_ev_skips_missing_odds(analyzer):
    """Mercados sin cuota se omiten del resultado."""
    probs = MatchProbabilities(
        home_win=0.5, draw=0.3, away_win=0.2,
        btts_yes=0.5, btts_no=0.5,
        over_25=0.5, under_25=0.5,
    )

    odds = {"home": 1.90}
    ev_results = analyzer._calculate_ev(probs, odds)
    selections = [r.selection for r in ev_results]
    assert "Local" in selections
    assert "Empate" not in selections


def test_calculate_ev_rejects_odds_below_one(analyzer):
    """Cuotas <= 1.0 se ignoran."""
    probs = MatchProbabilities(
        home_win=0.9, draw=0.05, away_win=0.05,
        btts_yes=0.5, btts_no=0.5,
        over_25=0.5, under_25=0.5,
    )

    odds = {"home": 1.0, "draw": 0.5, "away": 3.0}
    ev_results = analyzer._calculate_ev(probs, odds)
    selections = [r.selection for r in ev_results]
    assert "Local" not in selections
    assert "Empate" not in selections
    assert "Visitante" in selections


# ── Overround / Fair Odds ─────────────────────────────────

def test_remove_overround_typical():
    """Overround típico de ~5% en cuotas 1X2."""
    odds = {"home": 1.85, "draw": 3.40, "away": 4.20}
    ov = remove_overround(odds)
    # 1/1.85 + 1/3.40 + 1/4.20 ≈ 0.540 + 0.294 + 0.238 = 1.072 → 7.2%
    assert 0.05 < ov < 0.10


def test_remove_overround_no_margin():
    """Sin margen (cuotas justas), overround = 0."""
    odds = {"home": 2.0, "draw": 5.0, "away": 3.333}
    ov = remove_overround(odds)
    assert ov == pytest.approx(0.0, abs=0.01)


def test_fair_odds_increases_odds():
    """Cuota justa siempre >= cuota de mercado."""
    assert fair_odds(1.85, 0.05) > 1.85
    assert fair_odds(3.40, 0.05) > 3.40


def test_fair_odds_zero_overround():
    """Sin overround, cuota justa = cuota de mercado."""
    assert fair_odds(2.0, 0.0) == 2.0


def test_ev_uses_real_market_odds(analyzer):
    """EV se calcula con las cuotas reales de mercado (lo que cobras)."""
    probs = MatchProbabilities(
        home_win=0.6, draw=0.2, away_win=0.2,
        btts_yes=0.5, btts_no=0.5,
        over_25=0.5, under_25=0.5,
    )

    odds = {"home": 1.85, "draw": 3.40, "away": 4.20}
    ev_results = analyzer._calculate_ev(probs, odds)
    home_ev = next(x for x in ev_results if x.selection == "Local")
    # EV = prob * odds - 1 = 0.6 * 1.85 - 1 = 0.11 (11%)
    assert home_ev.ev_percent == pytest.approx(11.0, abs=0.5)
    assert home_ev.is_value is True


# ── Kelly Criterion ───────────────────────────────────────

def test_kelly_basic(analyzer):
    """Cálculo básico de Kelly."""
    kelly = analyzer._kelly_criterion(probability=0.55, odds=2.0)
    assert 9.9 <= kelly.kelly_full <= 10.1
    assert 4.9 <= kelly.kelly_half <= 5.1


def test_kelly_no_edge(analyzer):
    """Sin edge, Kelly debe ser 0."""
    kelly = analyzer._kelly_criterion(probability=0.40, odds=2.0)
    assert kelly.kelly_full == 0
    assert kelly.kelly_half == 0
    assert kelly.stake_units == 0


def test_kelly_capped(analyzer):
    """Kelly no debe exceder KELLY_CAP."""
    kelly = analyzer._kelly_criterion(probability=0.90, odds=3.0)
    assert kelly.kelly_full == 10.0
    assert kelly.kelly_half == 5.0


def test_kelly_invalid_odds(analyzer):
    """Cuotas <= 1.0 retornan Kelly vacío."""
    kelly = analyzer._kelly_criterion(probability=0.55, odds=1.0)
    assert kelly.kelly_full == 0
    assert kelly.stake_units == 0


def test_kelly_zero_probability(analyzer):
    """Probabilidad 0 retorna Kelly vacío."""
    kelly = analyzer._kelly_criterion(probability=0, odds=2.0)
    assert kelly.kelly_full == 0


def test_kelly_risk_levels(analyzer):
    """Verificar clasificación de riesgo."""
    kelly_low = analyzer._kelly_criterion(probability=0.51, odds=2.0)
    assert kelly_low.risk_level == "Bajo"

    kelly_high = analyzer._kelly_criterion(probability=0.70, odds=2.5)
    assert kelly_high.risk_level == "Alto"


# ── Form Multiplier (con decay temporal) ──────────────────

def test_form_empty_string():
    """Forma vacía retorna 1.0."""
    assert form_multiplier("") == 1.0


def test_form_too_short():
    """Menos de 3 resultados retorna 1.0."""
    assert form_multiplier("WL") == 1.0


def test_form_all_wins():
    """WWWWW debe dar multiplicador = 1.1 (máximo)."""
    mult = form_multiplier("WWWWW")
    assert mult == 1.1


def test_form_all_losses():
    """LLLLL debe dar multiplicador = 0.9 (mínimo)."""
    mult = form_multiplier("LLLLL")
    assert mult == 0.9


def test_form_all_draws():
    """DDDDD debe dar multiplicador = 1.0."""
    mult = form_multiplier("DDDDD")
    assert mult == 1.0


def test_form_decay_recent_wins_matter_more():
    """LLWWW (recientes ganan) debe dar más que WWWLL (recientes pierden)."""
    mult_recent_good = form_multiplier("LLWWW")  # Últimas 3 son W
    mult_recent_bad = form_multiplier("WWWLL")   # Últimas 2 son L
    assert mult_recent_good > mult_recent_bad


def test_form_decay_symmetric_different():
    """WLLLL vs LLLLW: el segundo tiene la W más reciente, debe ser mayor."""
    mult_old_win = form_multiplier("WLLLL")   # W es la más antigua
    mult_new_win = form_multiplier("LLLLW")   # W es la más reciente
    assert mult_new_win > mult_old_win


def test_form_takes_last_five():
    """Con más de 5 chars, toma solo los últimos 5."""
    mult = form_multiplier("LLLLLWWWWW")
    assert mult == 1.1


# ── H2H Adjustment ────────────────────────────────────────

def test_h2h_empty():
    """Sin datos H2H retorna (1.0, 1.0)."""
    assert h2h_adjustment([]) == (1.0, 1.0)


def test_h2h_too_few_matches():
    """Con menos de 3 partidos no aplica ajuste."""
    data = [
        {"home_goals": 2, "away_goals": 1, "home_winner": True},
        {"home_goals": 0, "away_goals": 1, "home_winner": False},
    ]
    assert h2h_adjustment(data) == (1.0, 1.0)


def test_h2h_minimum_three_matches():
    """Con exactamente 3 partidos aplica ajuste reducido (60%)."""
    data = [
        {"home_goals": 2, "away_goals": 0, "home_winner": True},
        {"home_goals": 1, "away_goals": 0, "home_winner": True},
        {"home_goals": 3, "away_goals": 1, "home_winner": True},
    ]
    home_adj, away_adj = h2h_adjustment(data)
    assert home_adj > 1.0   # Home domina
    assert away_adj < 1.0   # Away debilitado
    # Con 3 partidos, factor = 0.6, ajuste max = 0.08 * 0.6 * (1-0) = 0.048
    assert home_adj < 1.06  # Reducido por sample_factor


def test_h2h_five_matches_full_weight():
    """Con 5 partidos aplica el ajuste completo."""
    data = [
        {"home_goals": 2, "away_goals": 0, "home_winner": True},
        {"home_goals": 1, "away_goals": 0, "home_winner": True},
        {"home_goals": 3, "away_goals": 1, "home_winner": True},
        {"home_goals": 2, "away_goals": 1, "home_winner": True},
        {"home_goals": 1, "away_goals": 0, "home_winner": True},
    ]
    home_adj, away_adj = h2h_adjustment(data)
    # 5 partidos, todos home wins: rate=1.0, factor=1.0, adj=1+0.08=1.08
    assert home_adj == 1.08
    assert away_adj == 0.92


def test_h2h_balanced():
    """H2H equilibrado da ajustes cercanos a 1.0."""
    data = [
        {"home_goals": 2, "away_goals": 0, "home_winner": True},
        {"home_goals": 0, "away_goals": 2, "home_winner": False},
        {"home_goals": 1, "away_goals": 1, "home_winner": None},
    ]
    home_adj, away_adj = h2h_adjustment(data)
    assert abs(home_adj - 1.0) < 0.02
    assert abs(away_adj - 1.0) < 0.02


# ── Confidence Classification ─────────────────────────────

def test_confidence_alta():
    assert Analyzer._classify_confidence(15.0) == "Alta"


def test_confidence_media():
    assert Analyzer._classify_confidence(7.0) == "Media"


def test_confidence_baja():
    assert Analyzer._classify_confidence(2.0) == "Baja"


# ── Correct Score Matrix ──────────────────────────────────

def test_correct_scores_returns_top_5(analyzer):
    """Debe retornar exactamente 5 resultados."""
    scores = analyzer._correct_score_matrix(1.5, 1.2)
    assert len(scores) == 5


def test_correct_scores_ordered_by_probability(analyzer):
    """Resultados ordenados de mayor a menor probabilidad."""
    scores = analyzer._correct_score_matrix(1.5, 1.2)
    probs = [s["probability"] for s in scores]
    assert probs == sorted(probs, reverse=True)


def test_correct_scores_sum_reasonable(analyzer):
    """Top 5 resultados deben cubrir una porción significativa."""
    scores = analyzer._correct_score_matrix(1.5, 1.2)
    total_prob = sum(s["probability"] for s in scores)
    assert total_prob > 0.20


# ── Find Best Bet ─────────────────────────────────────────

def test_find_best_bet_returns_highest_ev(analyzer):
    """Debe retornar el EVResult con mayor EV."""
    results = [
        EVResult(selection="Local", ev=0.05, ev_percent=5, is_value=True),
        EVResult(selection="Over 2.5", ev=0.12, ev_percent=12, is_value=True),
        EVResult(selection="Empate", ev=0.02, ev_percent=2, is_value=False),
    ]
    best = analyzer._find_best_bet(results)
    assert best.selection == "Over 2.5"


def test_find_best_bet_none_when_no_value(analyzer):
    """Sin value bets, retorna None."""
    results = [
        EVResult(selection="Local", ev=-0.05, is_value=False),
        EVResult(selection="Empate", ev=-0.10, is_value=False),
    ]
    best = analyzer._find_best_bet(results)
    assert best is None


# ── Lambda Calculation ────────────────────────────────────

def test_lambdas_without_stats(analyzer):
    """Sin stats, lambdas usan media de liga + ventaja local."""
    lh, la, _, _, xg_used = analyzer._calculate_lambdas(None, None)
    assert lh > la
    assert xg_used is False


def test_lambdas_clamped(analyzer):
    """Lambdas deben estar dentro del rango permitido."""
    extreme_home = {"played": 29, "goals_for": 120, "goals_against": 5, "form": "WWWWW",
                    "home": {"played": 15, "goals_for": 70, "goals_against": 2,
                             "wins": 15, "draws": 0, "losses": 0}}
    extreme_away = {"played": 29, "goals_for": 5, "goals_against": 120, "form": "LLLLL",
                    "away": {"played": 14, "goals_for": 2, "goals_against": 70,
                             "wins": 0, "draws": 0, "losses": 14}}
    lh, la, _, _, _ = analyzer._calculate_lambdas(extreme_home, extreme_away)
    assert 0.2 <= la <= 3.5
    assert 0.3 <= lh <= 4.0


# ── Full Match Analysis ──────────────────────────────────

def test_analyze_match_basic(analyzer):
    """Análisis completo no debe fallar con datos básicos."""
    odds = {"home": 1.85, "draw": 3.40, "away": 4.20, "over_25": 2.10, "under_25": 1.75}
    home_stats = {
        "played": 29, "goals_for": 45, "goals_against": 30,
        "form": "WDWWL",
        "home": {"played": 15, "wins": 9, "draws": 3, "losses": 3,
                 "goals_for": 28, "goals_against": 12},
        "away": {"played": 14, "wins": 5, "draws": 4, "losses": 5,
                 "goals_for": 17, "goals_against": 18},
    }
    away_stats = {
        "played": 29, "goals_for": 30, "goals_against": 42,
        "form": "LDLWW",
        "home": {"played": 15, "wins": 5, "draws": 5, "losses": 5,
                 "goals_for": 18, "goals_against": 18},
        "away": {"played": 14, "wins": 3, "draws": 4, "losses": 7,
                 "goals_for": 12, "goals_against": 24},
    }

    analysis = analyzer.analyze_match(
        "Real Betis", "Espanyol", odds,
        home_stats=home_stats, away_stats=away_stats,
        commence_time="2026-04-04T18:30:00Z"
    )

    assert analysis.home_team == "Real Betis"
    assert analysis.away_team == "Espanyol"
    assert analysis.probabilities.home_win > 0
    assert len(analysis.ev_results) > 0
    assert len(analysis.correct_scores) == 5
    assert analysis.asian_handicap["lines"]


def test_analyze_match_no_stats(analyzer):
    """Análisis funciona sin stats (solo cuotas)."""
    odds = {"home": 2.50, "draw": 3.20, "away": 2.80}
    analysis = analyzer.analyze_match("Team A", "Team B", odds)
    assert analysis.probabilities.home_win > 0
    assert analysis.probabilities.draw > 0


# ── Correlation Detection ─────────────────────────────────

def test_correlation_no_value_bets():
    """Sin value bets, no hay correlaciones."""
    results = [
        EVResult(selection="Local", ev=-0.05, is_value=False),
        EVResult(selection="Over 2.5", ev=-0.03, is_value=False),
    ]
    warnings = EVCalculator.detect_correlated_bets(results)
    assert warnings == []


def test_correlation_single_value_bet():
    """Una sola value bet no puede estar correlacionada."""
    results = [
        EVResult(selection="Local", ev=0.10, is_value=True),
        EVResult(selection="Empate", ev=-0.05, is_value=False),
    ]
    warnings = EVCalculator.detect_correlated_bets(results)
    assert warnings == []


def test_correlation_local_over25():
    """Local + Over 2.5 son correlacionadas."""
    results = [
        EVResult(selection="Local", ev=0.10, is_value=True),
        EVResult(selection="Over 2.5", ev=0.08, is_value=True),
    ]
    warnings = EVCalculator.detect_correlated_bets(results)
    assert len(warnings) == 1
    assert "Correlación" in warnings[0]
    assert "Local" in warnings[0]


def test_correlation_btts_over25_redundant():
    """BTTS Sí + Over 2.5 son redundantes."""
    results = [
        EVResult(selection="BTTS Sí", ev=0.10, is_value=True),
        EVResult(selection="Over 2.5", ev=0.08, is_value=True),
    ]
    warnings = EVCalculator.detect_correlated_bets(results)
    assert len(warnings) == 1
    assert "redundantes" in warnings[0]


def test_correlation_empate_under25():
    """Empate + Under 2.5 son correlacionadas."""
    results = [
        EVResult(selection="Empate", ev=0.05, is_value=True),
        EVResult(selection="Under 2.5", ev=0.04, is_value=True),
    ]
    warnings = EVCalculator.detect_correlated_bets(results)
    assert len(warnings) == 1
    assert "Empate" in warnings[0]


def test_stake_adjustment_redundant_drops_lower_ev():
    """En bets redundantes, la de menor EV se descarta (multiplier=0)."""
    calc = EVCalculator()
    results = [
        EVResult(selection="BTTS Sí", ev=0.10, ev_percent=10, is_value=True),
        EVResult(selection="Over 2.5", ev=0.05, ev_percent=5, is_value=True),
    ]
    multipliers = calc.adjust_correlated_stakes(results)
    assert multipliers["BTTS Sí"] == 1.0  # Mayor EV, se mantiene
    assert multipliers["Over 2.5"] == 0.0  # Menor EV, se descarta


def test_stake_adjustment_correlated_reduces():
    """En bets correlacionadas (no redundantes), se reduce 30%."""
    calc = EVCalculator()
    results = [
        EVResult(selection="Local", ev=0.10, ev_percent=10, is_value=True),
        EVResult(selection="Over 2.5", ev=0.08, ev_percent=8, is_value=True),
    ]
    multipliers = calc.adjust_correlated_stakes(results)
    assert multipliers["Local"] == 0.70
    assert multipliers["Over 2.5"] == 0.70


def test_stake_adjustment_no_correlation():
    """Bets no correlacionadas mantienen stake completo."""
    calc = EVCalculator()
    results = [
        EVResult(selection="Local", ev=0.10, ev_percent=10, is_value=True),
        EVResult(selection="BTTS No", ev=0.05, ev_percent=5, is_value=True),
    ]
    multipliers = calc.adjust_correlated_stakes(results)
    assert multipliers["Local"] == 1.0
    assert multipliers["BTTS No"] == 1.0
