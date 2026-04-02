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
    is_value: bool = False


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
        self.kelly_cap = config.KELLY_CAP
        self.bankroll = config.BANKROLL_UNITS

    def calculate_ev(self, probs: MatchProbabilities, odds: dict) -> list[EVResult]:
        """
        Calcula EV para cada resultado posible.
        Descuenta el overround del bookmaker para no sobreestimar el edge.
        """
        results = []

        # Calcular overround del mercado 1X2
        overround = remove_overround(odds)

        outcomes = [
            ("Local", probs.home_win, odds.get("home")),
            ("Empate", probs.draw, odds.get("draw")),
            ("Visitante", probs.away_win, odds.get("away")),
            ("Over 2.5", probs.over_25, odds.get("over_25")),
            ("Under 2.5", probs.under_25, odds.get("under_25")),
            ("BTTS Sí", probs.btts_yes, odds.get("btts_yes")),
            ("BTTS No", probs.btts_no, odds.get("btts_no")),
        ]

        for name, prob, odd in outcomes:
            if odd and odd > 1.0:
                # Usar cuota justa (sin margen) para el cálculo de EV
                fair = fair_odds(odd, overround)
                ev = (prob * fair) - 1.0
                results.append(EVResult(
                    selection=name,
                    probability=round(prob, 4),
                    odds=odd,
                    ev=round(ev, 4),
                    ev_percent=round(ev * 100, 2),
                    is_value=bool((ev * 100) >= self.min_ev),
                ))

        return results

    def find_best_bet(self, ev_results: list[EVResult]) -> Optional[EVResult]:
        """Encuentra el resultado con mayor EV positivo."""
        value_bets = [r for r in ev_results if r.is_value]
        if not value_bets:
            return None
        return max(value_bets, key=lambda x: x.ev)

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
