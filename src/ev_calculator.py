"""
WinStake.ia — Calculadora de Expected Value y Kelly Criterion
Evalúa el valor esperado de apuestas y calcula sizing óptimo.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import config
from src.poisson_model import MatchProbabilities

logger = logging.getLogger(__name__)


@dataclass
class EVResult:
    """Resultado de cálculo de Expected Value."""
    selection: str = ""
    probability: float = 0.0
    odds: float = 0.0
    ev: float = 0.0
    ev_percent: float = 0.0
    is_value: bool = False       # EV >= MIN_EV_THRESHOLD (3%) — pick de valor pleno
    is_marginal: bool = False    # EV >= MARGINAL_EV_THRESHOLD (1%) y < 3% — valor marginal
    line: Optional[float] = None


@dataclass
class KellyResult:
    """Resultado del criterio de Kelly."""
    kelly_full: float = 0.0
    kelly_half: float = 0.0
    stake_units: float = 0.0
    risk_level: str = "Bajo"


def remove_overround(odds: dict) -> float:
    """
    Calcula el overround (margen del bookmaker) a partir de las cuotas 1X2.
    overround = sum(1/odds) - 1

    Returns:
        El overround como fracción (ej: 0.05 = 5% de margen)
    """
    h2h_keys = ["home", "draw", "away"]
    implied_sum = sum(1.0 / odds[k] for k in h2h_keys if k in odds and odds[k] and odds[k] > 1.0)
    if implied_sum <= 1.0:
        return 0.0
    return implied_sum - 1.0


def fair_odds(odds_value: float, overround: float) -> float:
    """
    Convierte cuota de mercado a cuota justa eliminando el margen.
    fair_odd = odds * (1 + overround)

    Esto equivale a dividir la probabilidad implícita entre el total
    del overround para "des-vigar" la cuota.
    """
    if odds_value <= 1.0:
        return odds_value
    return odds_value * (1.0 + overround)


class EVCalculator:
    """Calculadora de Expected Value y Kelly Criterion."""

    def __init__(self):
        self.min_ev = config.MIN_EV_THRESHOLD
        self.marginal_ev = config.MARGINAL_EV_THRESHOLD
        self.kelly_cap = config.KELLY_CAP
        self.bankroll = config.BANKROLL_UNITS

    def calculate_ev(self, probs: MatchProbabilities, odds: dict) -> list[EVResult]:
        """
        Calcula EV para cada resultado posible.

        Usa las cuotas reales de mercado (lo que realmente cobras) para
        el cálculo de EV, no las cuotas justas infladas.

        EV = (probabilidad_real × cuota_mercado) - 1
        """
        results = []

        outcomes = [
            # 1X2
            ("Local", probs.home_win, odds.get("home")),
            ("Empate", probs.draw, odds.get("draw")),
            ("Visitante", probs.away_win, odds.get("away")),
            # Doble Oportunidad
            ("1X", probs.double_chance_1x, odds.get("double_chance_1x")),
            ("X2", probs.double_chance_x2, odds.get("double_chance_x2")),
            ("12", probs.double_chance_12, odds.get("double_chance_12")),
            # Over/Under
            ("Over 1.5", probs.over_15, odds.get("over_15")),
            ("Under 1.5", probs.under_15, odds.get("under_15")),
            ("Over 2.5", probs.over_25, odds.get("over_25")),
            ("Under 2.5", probs.under_25, odds.get("under_25")),
            ("Over 3.5", probs.over_35, odds.get("over_35")),
            ("Under 3.5", probs.under_35, odds.get("under_35")),
            # BTTS
            ("BTTS Sí", probs.btts_yes, odds.get("btts_yes")),
            ("BTTS No", probs.btts_no, odds.get("btts_no")),
        ]

        # min_ev está en fracción (0.03 = 3%), ev también en fracción
        for name, prob, odd in outcomes:
            if odd and odd > 1.0:
                ev = (prob * odd) - 1.0
                ev_percent = round(ev * 100, 2)
                results.append(EVResult(
                    selection=name,
                    probability=round(prob, 4),
                    odds=odd,
                    ev=round(ev, 4),
                    ev_percent=ev_percent,
                    is_value=bool(ev >= self.min_ev),
                    is_marginal=bool(self.marginal_ev <= ev < self.min_ev),
                ))

        return results

    def find_best_bet(self, ev_results: list[EVResult]) -> Optional[EVResult]:
        """
        Encuentra el resultado con mayor EV positivo.
        Prioriza is_value (EV ≥ 3%); si no hay ninguno, sube el mejor is_marginal (1-3%).
        """
        value_bets = [r for r in ev_results if r.is_value]
        if value_bets:
            return max(value_bets, key=lambda x: x.ev)
        marginal_bets = [r for r in ev_results if r.is_marginal]
        if marginal_bets:
            return max(marginal_bets, key=lambda x: x.ev)
        return None

    def kelly_criterion(self, probability: float, odds: float) -> KellyResult:
        """Calcula el criterio de Kelly para sizing de apuesta."""
        if odds <= 1.0 or probability <= 0:
            return KellyResult()

        kelly_full = ((probability * odds) - 1) / (odds - 1)
        kelly_full = max(0, min(kelly_full, self.kelly_cap))
        kelly_half = kelly_full / 2

        stake = round(kelly_half * self.bankroll, 1)

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
    def classify_confidence(ev_percent: float) -> str:
        """Clasifica nivel de confianza basado en el EV%."""
        if ev_percent >= 10:
            return "Alta"
        elif ev_percent >= 5:
            return "Media"
        else:
            return "Baja"

    def calculate_ev_nba(self, probs, odds: dict) -> list[EVResult]:
        """
        Calcula EV para mercados NBA: moneyline, spread, totals.

        Args:
            probs: NBAMatchProbabilities
            odds: dict con claves home, away, spread_home, spread_away, over, under
        """
        results = []

        outcomes = [
            # Moneyline
            ("Home", probs.home_win, odds.get("home"), None),
            ("Away", probs.away_win, odds.get("away"), None),
            # Spread
            ("Spread Home", probs.home_cover_prob, odds.get("spread_home"), odds.get("spread_line")),
            ("Spread Away", probs.away_cover_prob, odds.get("spread_away"), -odds.get("spread_line") if odds.get("spread_line") is not None else None),
            # Totals
            ("Over", probs.over_total, odds.get("over"), odds.get("total_line")),
            ("Under", probs.under_total, odds.get("under"), odds.get("total_line")),
        ]

        for name, prob, odd, line in outcomes:
            if not (odd and odd > 1.0 and prob > 0):
                continue

            ev = (prob * odd) - 1.0
            ev_percent = round(ev * 100, 2)

            is_value = bool(ev >= self.min_ev)

            # ── Filtros de cordura para moneyline NBA ──────────
            if name in ("Home", "Away") and is_value:
                market_implied = 1.0 / odd

                # 1. No recomendar underdogs extremos (odds > 4.0):
                #    nuestro modelo carece de resolución para ese rango
                if odd > 4.0:
                    is_value = False

                # 2. No recomendar favoritos aplastantes (odds < 1.25):
                #    el payout es tan bajo que nunca hay valor real
                elif odd < 1.25:
                    is_value = False

                # 3. Ratio de discrepancia: si el modelo es >2.0× más
                #    optimista que el mercado, probablemente la diferencia
                #    se debe a información que no tenemos (lesiones, etc.)
                elif market_implied > 0 and (prob / market_implied) > 2.0:
                    is_value = False

                # 4. EV irrealmente alto (>40%): el modelo diverge demasiado
                #    del mercado. Casi nunca existe edge real de esta magnitud
                #    en NBA (especialmente fin de temporada, equipos malos).
                elif ev_percent > 40.0:
                    is_value = False

            results.append(EVResult(
                selection=name,
                probability=round(prob, 4),
                odds=odd,
                ev=round(ev, 4),
                ev_percent=ev_percent,
                is_value=is_value,
                is_marginal=bool(self.marginal_ev <= ev < self.min_ev and not is_value),
                line=line,
            ))

        return results

    @staticmethod
    def detect_correlated_bets_nba(ev_results: list[EVResult]) -> list[str]:
        """Detecta value bets correlacionadas en partidos NBA."""
        value_selections = {r.selection for r in ev_results if r.is_value}
        if len(value_selections) < 2:
            return []

        warnings = []

        # Spread + Moneyline son altamente correlacionados
        if "Home" in value_selections and "Spread Home" in value_selections:
            warnings.append(
                "Correlacion: Home ML + Spread Home son redundantes. "
                "Apostar solo al de mayor EV."
            )
        if "Away" in value_selections and "Spread Away" in value_selections:
            warnings.append(
                "Correlacion: Away ML + Spread Away son redundantes. "
                "Apostar solo al de mayor EV."
            )

        # Over + favorito correlacionados (parcialmente)
        if ("Home" in value_selections or "Away" in value_selections) and "Over" in value_selections:
            warnings.append(
                "Correlacion parcial: Moneyline + Over. "
                "Reducir stake combinado un 20%."
            )

        return warnings

    @staticmethod
    def detect_correlated_bets(ev_results: list[EVResult]) -> list[str]:
        """
        Detecta value bets correlacionadas en el mismo partido.

        Grupos correlacionados:
        - 1X2: Local, Empate, Visitante (mutuamente excluyentes, no correlacionadas entre sí)
        - Goles: Over 2.5 ↔ Local/Visitante (favorito gana → más goles probable)
        - BTTS: BTTS Sí ↔ Over 2.5 (ambos equipos marcan → casi siempre over)

        Returns:
            Lista de advertencias sobre correlaciones detectadas.
        """
        value_selections = {r.selection for r in ev_results if r.is_value}
        if len(value_selections) < 2:
            return []

        warnings = []

        # Correlación: resultado + totales
        result_bets = value_selections & {"Local", "Visitante"}
        if result_bets and "Over 2.5" in value_selections:
            team = next(iter(result_bets))
            warnings.append(
                f"Correlación: {team} + Over 2.5 están correlacionados. "
                f"Reducir stake combinado un 30%."
            )

        # Correlación: BTTS + Over 2.5
        if "BTTS Sí" in value_selections and "Over 2.5" in value_selections:
            warnings.append(
                "Correlación: BTTS Sí + Over 2.5 son altamente redundantes. "
                "Apostar solo al de mayor EV."
            )

        # Correlación: Empate + Under 2.5
        if "Empate" in value_selections and "Under 2.5" in value_selections:
            warnings.append(
                "Correlación: Empate + Under 2.5 están correlacionados. "
                "Reducir stake combinado un 25%."
            )

        # Correlación: BTTS No + Under 2.5
        if "BTTS No" in value_selections and "Under 2.5" in value_selections:
            warnings.append(
                "Correlación: BTTS No + Under 2.5 son redundantes. "
                "Apostar solo al de mayor EV."
            )

        return warnings

    def adjust_correlated_stakes(
        self, ev_results: list[EVResult]
    ) -> dict[str, float]:
        """
        Calcula stakes ajustados cuando hay bets correlacionadas.

        Aplica un factor de reducción a bets que comparten riesgo:
        - Bets redundantes (BTTS Sí + Over 2.5): solo la de mayor EV
        - Bets correlacionadas (Local + Over 2.5): reducir 30% cada una

        Returns:
            Dict {selection: stake_multiplier} donde 1.0 = sin ajuste, 0.0 = no apostar
        """
        value_bets = [r for r in ev_results if r.is_value]
        value_selections = {r.selection for r in value_bets}
        multipliers = {r.selection: 1.0 for r in value_bets}

        if len(value_bets) < 2:
            return multipliers

        # Redundantes: solo apostar al de mayor EV
        redundant_pairs = [
            ("BTTS Sí", "Over 2.5"),
            ("BTTS No", "Under 2.5"),
        ]
        for a, b in redundant_pairs:
            if a in value_selections and b in value_selections:
                ev_a = next(r.ev for r in value_bets if r.selection == a)
                ev_b = next(r.ev for r in value_bets if r.selection == b)
                loser = b if ev_a >= ev_b else a
                multipliers[loser] = 0.0

        # Correlacionadas: reducir 30%
        correlated_pairs = [
            ({"Local", "Visitante"}, "Over 2.5", 0.70),
            ({"Empate"}, "Under 2.5", 0.75),
        ]
        for result_set, totals_bet, factor in correlated_pairs:
            matched = result_set & value_selections
            if matched and totals_bet in value_selections:
                for sel in matched:
                    multipliers[sel] = min(multipliers[sel], factor)
                multipliers[totals_bet] = min(multipliers[totals_bet], factor)

        return multipliers
