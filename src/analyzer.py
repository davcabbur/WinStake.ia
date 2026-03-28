"""
WinStake.ia — Motor de Análisis Cuantitativo
Modelos: Poisson, Expected Value, Kelly Criterion, Detección de Edge.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Optional

from scipy.stats import poisson

import config
from src.xg_estimator import XGEstimator, XG_WEIGHT

logger = logging.getLogger(__name__)


@dataclass
class MatchProbabilities:
    """Probabilidades estimadas para un partido."""
    home_win: float = 0.0
    draw: float = 0.0
    away_win: float = 0.0
    over_25: float = 0.0
    under_25: float = 0.0
    btts_yes: float = 0.0
    btts_no: float = 0.0
    lambda_home: float = 0.0
    lambda_away: float = 0.0
    xg_home: float = 0.0        # xG por partido del equipo local
    xg_away: float = 0.0        # xG por partido del equipo visitante
    xg_used: bool = False       # Si se usó xG en el cálculo


@dataclass
class EVResult:
    """Resultado de cálculo de Expected Value."""
    selection: str = ""
    probability: float = 0.0
    odds: float = 0.0
    ev: float = 0.0
    ev_percent: float = 0.0
    is_value: bool = False


@dataclass
class KellyResult:
    """Resultado del criterio de Kelly."""
    kelly_full: float = 0.0
    kelly_half: float = 0.0
    stake_units: float = 0.0
    risk_level: str = "Bajo"


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

    def analyze_match(
        self,
        home_team: str,
        away_team: str,
        odds: dict,
        home_stats: Optional[dict] = None,
        away_stats: Optional[dict] = None,
        commence_time: str = "",
    ) -> MatchAnalysis:
        """
        Análisis completo de un partido.

        Args:
            home_team: Nombre del equipo local
            away_team: Nombre del equipo visitante
            odds: Dict con cuotas: {"home": X.XX, "draw": X.XX, "away": X.XX, ...}
            home_stats: Stats del local (de standings)
            away_stats: Stats del visitante (de standings)
            commence_time: Fecha/hora del partido

        Returns:
            MatchAnalysis con todos los resultados
        """
        analysis = MatchAnalysis(
            home_team=home_team,
            away_team=away_team,
            commence_time=commence_time,
            market_odds=odds,
        )

        # 1. Calcular lambdas (goles esperados) — con xG si disponible
        lambda_home, lambda_away, xg_home, xg_away, xg_used = self._calculate_lambdas(
            home_stats, away_stats
        )

        # 2. Calcular probabilidades vía Poisson
        probs = self._poisson_probabilities(lambda_home, lambda_away)
        probs.xg_home = xg_home
        probs.xg_away = xg_away
        probs.xg_used = xg_used
        analysis.probabilities = probs

        # 3. Calcular EV para cada resultado
        ev_results = self._calculate_ev(probs, odds)
        analysis.ev_results = ev_results

        # 4. Encontrar mejor apuesta
        best = self._find_best_bet(ev_results)
        analysis.best_bet = best

        # 5. Kelly criterion
        if best and best.is_value:
            kelly = self._kelly_criterion(best.probability, best.odds)
            analysis.kelly = kelly
            analysis.confidence = self._classify_confidence(best.ev_percent)
            analysis.recommendation = f"{best.selection} @ {best.odds:.2f}"
        else:
            analysis.recommendation = "No apostar"
            analysis.confidence = "—"

        # 6. Generar insights
        analysis.insights = self._generate_insights(
            home_team, away_team, probs, odds, home_stats, away_stats, best
        )

        return analysis

    def _calculate_lambdas(
        self,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
    ) -> tuple[float, float, float, float, bool]:
        """
        Calcula los parámetros λ (goles esperados) para cada equipo.
        Usa xG si está disponible, mezclado con goles reales.

        Returns:
            (lambda_home, lambda_away, xg_home, xg_away, xg_used)
        """
        avg_goals_per_team = self.league_avg_goals / 2  # ~1.325
        xg_home_val = 0.0
        xg_away_val = 0.0
        xg_used = False

        if home_stats and away_stats:
            # Fuerza atacante/defensiva relativa a la media
            home_played = home_stats.get("played", 29) or 29
            away_played = away_stats.get("played", 29) or 29

            home_attack = (home_stats["goals_for"] / home_played) / avg_goals_per_team
            home_defense = (home_stats["goals_against"] / home_played) / avg_goals_per_team
            away_attack = (away_stats["goals_for"] / away_played) / avg_goals_per_team
            away_defense = (away_stats["goals_against"] / away_played) / avg_goals_per_team

            # λ = Ataque equipo × Defensa rival × Media de la liga × Factor casa
            lambda_home = home_attack * away_defense * avg_goals_per_team
            lambda_away = away_attack * home_defense * avg_goals_per_team

            # Ajuste por ventaja local
            lambda_home *= (1 + self.home_advantage)
            lambda_away *= (1 - self.home_advantage * 0.5)

            # ── xG Integration ────────────────────────────────
            # Si tenemos datos de xG, mezclar con goles reales
            home_xg_pm = home_stats.get("xg_for_per_match", 0)
            away_xg_pm = away_stats.get("xg_for_per_match", 0)
            home_xga_pm = home_stats.get("xg_against_per_match", 0)
            away_xga_pm = away_stats.get("xg_against_per_match", 0)

            if home_xg_pm > 0 and away_xg_pm > 0:
                xg_used = True
                xg_home_val = home_xg_pm
                xg_away_val = away_xg_pm

                # Calcular lambdas basados en xG
                home_xg_attack = home_xg_pm / avg_goals_per_team
                away_xg_defense = away_xga_pm / avg_goals_per_team
                away_xg_attack = away_xg_pm / avg_goals_per_team
                home_xg_defense = home_xga_pm / avg_goals_per_team

                lambda_home_xg = home_xg_attack * away_xg_defense * avg_goals_per_team
                lambda_away_xg = away_xg_attack * home_xg_defense * avg_goals_per_team

                # Ajuste ventaja local también al xG
                lambda_home_xg *= (1 + self.home_advantage)
                lambda_away_xg *= (1 - self.home_advantage * 0.5)

                # Mezclar xG con goles reales (XG_WEIGHT = 0.65)
                lambda_home = XGEstimator.blend_xg_with_goals(
                    lambda_home_xg, lambda_home, XG_WEIGHT
                )
                lambda_away = XGEstimator.blend_xg_with_goals(
                    lambda_away_xg, lambda_away, XG_WEIGHT
                )

                logger.debug(
                    f"xG blend: home λ={lambda_home:.2f} (xG:{lambda_home_xg:.2f}, "
                    f"goals:{home_attack * away_defense * avg_goals_per_team:.2f})"
                )
            else:
                # Sin xG: usar datos local/visitante si disponibles
                if "home" in home_stats and home_stats["home"]["played"] > 0:
                    home_home_gf = home_stats["home"]["goals_for"] / home_stats["home"]["played"]
                    lambda_home = lambda_home * (1 - self.form_weight) + home_home_gf * self.form_weight

                if "away" in away_stats and away_stats["away"]["played"] > 0:
                    away_away_gf = away_stats["away"]["goals_for"] / away_stats["away"]["played"]
                    lambda_away = lambda_away * (1 - self.form_weight) + away_away_gf * self.form_weight

        else:
            # Sin datos → usar cuotas implícitas como proxy
            lambda_home = avg_goals_per_team * (1 + self.home_advantage)
            lambda_away = avg_goals_per_team * (1 - self.home_advantage * 0.5)

        # Clamp razonable
        lambda_home = max(0.3, min(4.0, lambda_home))
        lambda_away = max(0.2, min(3.5, lambda_away))

        return round(lambda_home, 3), round(lambda_away, 3), round(xg_home_val, 2), round(xg_away_val, 2), xg_used

    def _poisson_probabilities(
        self, lambda_home: float, lambda_away: float
    ) -> MatchProbabilities:
        """Genera distribución de probabilidades usando modelo Poisson."""
        home_win = 0.0
        draw = 0.0
        away_win = 0.0
        over_25 = 0.0
        btts_yes = 0.0

        # Probabilidad de que home marque 0
        p_home_zero = poisson.pmf(0, lambda_home)
        # Probabilidad de que away marque 0
        p_away_zero = poisson.pmf(0, lambda_away)

        for h in range(self.max_goals + 1):
            for a in range(self.max_goals + 1):
                p = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)

                if h > a:
                    home_win += p
                elif h == a:
                    draw += p
                else:
                    away_win += p

                if h + a > 2:
                    over_25 += p

                if h > 0 and a > 0:
                    btts_yes += p

        # Normalizar a 100%
        total_1x2 = home_win + draw + away_win
        if total_1x2 > 0:
            home_win /= total_1x2
            draw /= total_1x2
            away_win /= total_1x2

        under_25 = 1.0 - over_25
        btts_no = 1.0 - btts_yes

        return MatchProbabilities(
            home_win=round(home_win, 4),
            draw=round(draw, 4),
            away_win=round(away_win, 4),
            over_25=round(over_25, 4),
            under_25=round(under_25, 4),
            btts_yes=round(btts_yes, 4),
            btts_no=round(btts_no, 4),
            lambda_home=lambda_home,
            lambda_away=lambda_away,
        )

    def _calculate_ev(self, probs: MatchProbabilities, odds: dict) -> list[EVResult]:
        """Calcula EV para cada resultado posible."""
        results = []

        outcomes = [
            ("Local", probs.home_win, odds.get("home")),
            ("Empate", probs.draw, odds.get("draw")),
            ("Visitante", probs.away_win, odds.get("away")),
            ("Over 2.5", probs.over_25, odds.get("over_25")),
            ("Under 2.5", probs.under_25, odds.get("under_25")),
        ]

        for name, prob, odd in outcomes:
            if odd and odd > 1.0:
                ev = (prob * odd) - 1.0
                results.append(EVResult(
                    selection=name,
                    probability=round(prob, 4),
                    odds=odd,
                    ev=round(ev, 4),
                    ev_percent=round(ev * 100, 2),
                    is_value=ev >= self.min_ev,
                ))

        return results

    def _find_best_bet(self, ev_results: list[EVResult]) -> Optional[EVResult]:
        """Encuentra el resultado con mayor EV positivo."""
        value_bets = [r for r in ev_results if r.is_value]
        if not value_bets:
            return None
        return max(value_bets, key=lambda x: x.ev)

    def _kelly_criterion(self, probability: float, odds: float) -> KellyResult:
        """Calcula el criterio de Kelly para sizing de apuesta."""
        if odds <= 1.0 or probability <= 0:
            return KellyResult()

        kelly_full = ((probability * odds) - 1) / (odds - 1)
        kelly_full = max(0, min(kelly_full, self.kelly_cap))  # Cap
        kelly_half = kelly_full / 2

        stake = round(kelly_half * self.bankroll, 1)

        # Nivel de riesgo
        if kelly_half <= 0.02:
            risk = "Bajo"
        elif kelly_half <= 0.04:
            risk = "Moderado"
        else:
            risk = "Alto"

        return KellyResult(
            kelly_full=round(kelly_full * 100, 2),
            kelly_half=round(kelly_half * 100, 2),
            stake_units=stake,
            risk_level=risk,
        )

    @staticmethod
    def _classify_confidence(ev_percent: float) -> str:
        """Clasifica nivel de confianza basado en el EV%."""
        if ev_percent >= 10:
            return "Alta"
        elif ev_percent >= 5:
            return "Media"
        else:
            return "Baja"

    def _generate_insights(
        self,
        home_team: str,
        away_team: str,
        probs: MatchProbabilities,
        odds: dict,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
        best_bet: Optional[EVResult],
    ) -> list[str]:
        """Genera insights estilo Moneyball basados en datos."""
        insights = []

        # Insight de goles esperados
        total_lambda = probs.lambda_home + probs.lambda_away
        insights.append(
            f"Goles esperados: {home_team} {probs.lambda_home:.1f} — "
            f"{away_team} {probs.lambda_away:.1f} (Total: {total_lambda:.1f})"
        )

        if home_stats and away_stats:
            # Diferencial de calidad
            diff = home_stats.get("goal_diff", 0) - away_stats.get("goal_diff", 0)
            if abs(diff) > 20:
                better = home_team if diff > 0 else away_team
                insights.append(f"Diferencial de calidad muy alto: {better} es claramente superior (+{abs(diff)} GD)")

            # Equipo de empates
            if home_stats.get("draws", 0) >= 9:
                insights.append(f"{home_team} empata mucho ({home_stats['draws']} en {home_stats['played']} partidos)")
            if away_stats.get("draws", 0) >= 9:
                insights.append(f"{away_team} empata mucho ({away_stats['draws']} en {away_stats['played']} partidos)")

            # Equipo defensivo
            home_gf_avg = home_stats["goals_for"] / max(home_stats["played"], 1)
            away_gf_avg = away_stats["goals_for"] / max(away_stats["played"], 1)
            if home_gf_avg < 1.0:
                insights.append(f"⚠️ {home_team} es muy poco goleador ({home_gf_avg:.1f} GF/partido)")
            if away_gf_avg < 1.0:
                insights.append(f"⚠️ {away_team} es muy poco goleador ({away_gf_avg:.1f} GF/partido)")

            # Zona de descenso / Europa
            if home_stats.get("rank", 20) >= 18:
                insights.append(f"🔴 {home_team} en zona de descenso — motivación máxima")
            elif home_stats.get("rank", 20) <= 4:
                insights.append(f"🟢 {home_team} en zona Champions — alta motivación")

            if away_stats.get("rank", 20) >= 18:
                insights.append(f"🔴 {away_team} en zona de descenso — motivación máxima")
            elif away_stats.get("rank", 20) <= 4:
                insights.append(f"🟢 {away_team} en zona Champions — alta motivación")

        # Market inefficiency
        if odds.get("home"):
            implied_home = 1 / odds["home"]
            edge_home = probs.home_win - implied_home
            if abs(edge_home) > 0.08:
                if edge_home > 0:
                    insights.append(f"⚡ {home_team} infravalorado por el mercado ({edge_home*100:.1f}% edge)")
                else:
                    insights.append(f"📊 {home_team} sobrevalorado por el mercado ({edge_home*100:.1f}% spread)")

        if odds.get("away"):
            implied_away = 1 / odds["away"]
            edge_away = probs.away_win - implied_away
            if abs(edge_away) > 0.08:
                if edge_away > 0:
                    insights.append(f"⚡ {away_team} infravalorado por el mercado ({edge_away*100:.1f}% edge)")
                else:
                    insights.append(f"📊 {away_team} sobrevalorado por el mercado ({edge_away*100:.1f}% spread)")

        if not best_bet:
            insights.append("❌ Sin edge: mercado bien calibrado para este partido")

        return insights


def odds_to_implied_probability(odds: float) -> float:
    """Convierte cuota decimal a probabilidad implícita."""
    if odds <= 1.0:
        return 0.0
    return 1.0 / odds


def remove_overround(probs: dict[str, float]) -> dict[str, float]:
    """Elimina el margen de la casa de las probabilidades implícitas."""
    total = sum(probs.values())
    if total <= 0:
        return probs
    return {k: v / total for k, v in probs.items()}
