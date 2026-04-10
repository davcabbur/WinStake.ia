"""
WinStake.ia — Blowout & Garbage Time Adjuster
Detecta victorias cómodas proyectadas y aplica dos tipos de ajuste:

  1. Over del total: en blowouts el pace cae en Q4 (titulares del ganador
     se sientan, el perdedor no ejecuta bien) → total final 3-6 pts menor.

  2. Props de asistencias/PRA de forwards: titulares se retiran antes en
     blowouts → menos minutos reales → confianza reducida en AST/PRA.
"""

from dataclasses import dataclass
from scipy.stats import norm as _norm


@dataclass
class BlowoutContext:
    """Contexto de blowout para un partido NBA."""
    projected_spread: float   # Margen esperado (valor absoluto, pts)
    blowout_prob: float        # P(margen final > 15 pts)
    is_blowout: bool           # True si blowout_prob > 0.30
    is_close: bool             # True si spread proyectado ≤ 5.0 pts
    favored_team: str = ""     # "home" | "away" | "" (equilibrado)


def detect_blowout(
    home_score: float,
    away_score: float,
    std_diff: float,
) -> BlowoutContext:
    """
    Calcula el contexto de blowout a partir de los scores proyectados.

    Usa la distribución Normal de la diferencia de puntos para estimar
    P(margen > 15), umbral histórico donde el Q4 pierde competitividad.

    Args:
        home_score: Puntos esperados del equipo local
        away_score: Puntos esperados del visitante
        std_diff:   Desviación estándar de la diferencia (√(σ_home² + σ_away²))
    """
    spread = home_score - away_score   # positivo = home favorito
    abs_spread = abs(spread)

    if std_diff > 0:
        blowout_prob = float(_norm.sf(15.0, loc=abs_spread, scale=std_diff))
    else:
        blowout_prob = 1.0 if abs_spread > 15 else 0.0

    blowout_prob = round(min(1.0, max(0.0, blowout_prob)), 3)
    favored = "home" if spread > 0 else ("away" if spread < 0 else "")

    return BlowoutContext(
        projected_spread=round(abs_spread, 1),
        blowout_prob=blowout_prob,
        is_blowout=blowout_prob > 0.30,
        is_close=abs_spread <= 5.0,
        favored_team=favored,
    )


def adjust_over_for_blowout(
    over_prob: float,
    blowout_ctx: BlowoutContext,
) -> float:
    """
    Reduce la probabilidad de Over en partidos proyectados como blowout.

    El equipo líder saca titulares en Q4, el pace baja y el perdedor
    no ataca con urgencia hasta el final del período. El total final
    suele ser 3-6 pts inferior a la proyección normal.

    Reducción: 0% (blowout_prob=0.30) → 10% relativo (blowout_prob≥0.70).
    """
    if not blowout_ctx.is_blowout:
        return over_prob

    reduction = min(0.10, (blowout_ctx.blowout_prob - 0.30) / 0.40 * 0.10)
    return round(max(0.01, over_prob * (1.0 - reduction)), 4)


def adjust_prop_confidence_for_blowout(
    confidence: float,
    stat_key: str,
    pos: str,
    blowout_ctx: BlowoutContext,
) -> float:
    """
    Penaliza la confianza en props de asistencias/PRA de forwards
    cuando se proyecta un partido desequilibrado.

    Afecta únicamente forwards (pos == 'F') y stats 'ast' / 'pra'.
    Penalización: 0.05 (blowout_prob=0.30) → 0.15 (blowout_prob≥0.70).
    """
    if not blowout_ctx.is_blowout:
        return confidence
    if pos != "F" or stat_key not in ("ast", "pra"):
        return confidence

    penalty = min(0.15, 0.05 + (blowout_ctx.blowout_prob - 0.30) / 0.40 * 0.10)
    return round(max(0.0, confidence - penalty), 3)
