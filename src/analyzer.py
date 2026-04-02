"""
WinStake.ia — Motor de Análisis Cuantitativo
Fachada que orquesta: PoissonModel, EVCalculator y MarketAnalyzer.

Todos los tipos se re-exportan aquí para mantener compatibilidad con
los imports existentes (main.py, database.py, formatter.py, etc.).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import config

# Re-exportar tipos para compatibilidad
from src.poisson_model import MatchProbabilities, PoissonModel
from src.ev_calculator import EVResult, KellyResult, EVCalculator
from src.market_analyzer import form_multiplier, h2h_adjustment, generate_insights

logger = logging.getLogger(__name__)


@dataclass
class MatchAnalysis:
    """Análisis completo de un partido."""
    home_team: str = ""
    away_team: str = ""
    commence_time: str = ""
    probabilities: MatchProbabilities = field(default_factory=MatchProbabilities)
    market_odds: dict = field(default_factory=dict)
    ev_results: list = field(default_factory=list)
    best_bet: Optional[EVResult] = None
    kelly: Optional[KellyResult] = None
    confidence: str = "Baja"
    insights: list = field(default_factory=list)
    recommendation: str = "No apostar"
    correct_scores: list = field(default_factory=list)
    asian_handicap: dict = field(default_factory=dict)


class Analyzer:
    """Motor de análisis cuantitativo para apuestas de fútbol."""

    def __init__(self):
        self.home_advantage = config.HOME_ADVANTAGE
        self.form_weight = config.FORM_WEIGHT
        self.league_avg_goals = config.LEAGUE_AVG_GOALS
        self.max_goals = config.MAX_GOALS_MODEL
        self.min_ev = config.MIN_EV_THRESHOLD
        self.kelly_cap = config.KELLY_CAP
        self.bankroll = config.BANKROLL_UNITS

        self._poisson = PoissonModel()
        self._ev_calc = EVCalculator()

    def analyze_match(
        self,
        home_team: str,
        away_team: str,
        odds: dict,
        home_stats: Optional[dict] = None,
        away_stats: Optional[dict] = None,
        commence_time: str = "",
        h2h_data: Optional[list] = None,
    ) -> MatchAnalysis:
        """Análisis completo de un partido."""
        analysis = MatchAnalysis(
            home_team=home_team,
            away_team=away_team,
            commence_time=commence_time,
            market_odds=odds,
        )

        # 1. Calcular lambdas (goles esperados)
        lambda_home, lambda_away, xg_home, xg_away, xg_used = self._calculate_lambdas(
            home_stats, away_stats, h2h_data
        )

        # 2. Probabilidades vía Poisson
        probs = self._poisson.poisson_probabilities(lambda_home, lambda_away)
        probs.xg_home = xg_home
        probs.xg_away = xg_away
        probs.xg_used = xg_used
        analysis.probabilities = probs

        # 3. Calcular EV (con descuento de overround)
        ev_results = self._ev_calc.calculate_ev(probs, odds)
        analysis.ev_results = ev_results

        # 4. Mejor apuesta
        best = self._ev_calc.find_best_bet(ev_results)
        analysis.best_bet = best

        # 5. Kelly criterion
        if best and best.is_value:
            kelly = self._ev_calc.kelly_criterion(best.probability, best.odds)
            analysis.kelly = kelly
            analysis.confidence = self._ev_calc.classify_confidence(best.ev_percent)
            analysis.recommendation = f"{best.selection} @ {best.odds:.2f}"
        else:
            analysis.recommendation = "No apostar"
            analysis.confidence = "—"

        # 6. Correct Score
        analysis.correct_scores = self._poisson.correct_score_matrix(
            probs.lambda_home, probs.lambda_away
        )

        # 7. Hándicap Asiático
        analysis.asian_handicap = self._poisson.asian_handicap(
            probs.lambda_home, probs.lambda_away, odds
        )

        # 8. Insights
        analysis.insights = generate_insights(
            home_team, away_team, probs, odds, home_stats, away_stats, best, h2h_data
        )

        # 9. Detección de correlación entre mercados
        correlation_warnings = self._ev_calc.detect_correlated_bets(ev_results)
        if correlation_warnings:
            analysis.insights.extend(f"⚠️ {w}" for w in correlation_warnings)

        return analysis

    def _calculate_lambdas(
        self,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
        h2h_data: Optional[list] = None,
    ) -> tuple[float, float, float, float, bool]:
        """Delega el cálculo de lambdas al PoissonModel."""
        return self._poisson.calculate_lambdas(
            home_stats, away_stats, h2h_data,
            form_multiplier_fn=form_multiplier,
            h2h_adjustment_fn=h2h_adjustment,
        )

    # ── Métodos delegados (compatibilidad con tests existentes) ──

    def _poisson_probabilities(self, lambda_home, lambda_away):
        return self._poisson.poisson_probabilities(lambda_home, lambda_away)

    def _calculate_ev(self, probs, odds):
        return self._ev_calc.calculate_ev(probs, odds)

    def _correct_score_matrix(self, lambda_home, lambda_away, top_n=5):
        return self._poisson.correct_score_matrix(lambda_home, lambda_away, top_n)

    def _asian_handicap(self, lambda_home, lambda_away, odds):
        return self._poisson.asian_handicap(lambda_home, lambda_away, odds)

    def _find_best_bet(self, ev_results):
        return self._ev_calc.find_best_bet(ev_results)

    def _kelly_criterion(self, probability, odds):
        return self._ev_calc.kelly_criterion(probability, odds)

    @staticmethod
    def _classify_confidence(ev_percent):
        return EVCalculator.classify_confidence(ev_percent)

    @staticmethod
    def _form_multiplier(form_str):
        return form_multiplier(form_str)

    @staticmethod
    def _h2h_adjustment(h2h_data):
        return h2h_adjustment(h2h_data)
