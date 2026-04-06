"""
WinStake.ia — Estimador de Expected Goals (xG)
Calcula xG a partir de datos de tiros disponibles en API-Football.

Modelo simplificado basado en probabilidades de conversión por zona:
- Tiro dentro del área:  ~0.12 xG (12% conversión histórica)
- Tiro fuera del área:   ~0.03 xG (3% conversión histórica)
- Tiro a puerta:         ~0.10 xG extra (refinamiento por precisión)

Referencia: Estas tasas están alineadas con los modelos xG de
StatsBomb, Opta y FBref para las principales ligas europeas.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Tasas de conversión por tipo de tiro ──────────────────
# Basadas en promedios de las top 5 ligas europeas (2020-2025)
XG_RATE_INSIDE_BOX = 0.12      # 12% de los tiros dentro del área son gol
XG_RATE_OUTSIDE_BOX = 0.03     # 3% de los tiros fuera del área
XG_RATE_ON_TARGET = 0.33       # 33% de los tiros a puerta son gol
XG_RATE_BLOCKED = 0.02         # 2% de los tiros bloqueados (rebote/desvío)

# Peso para mezclar xG con goles reales en el modelo
XG_WEIGHT = 0.50               # 50% xG, 50% goles reales (equilibrado para >25 jornadas)


class XGEstimator:
    """Estima xG (Expected Goals) a partir de estadísticas de tiros."""

    @staticmethod
    def estimate_xg_from_stats(
        shots_on_goal: int = 0,
        shots_off_goal: int = 0,
        shots_inside_box: int = 0,
        shots_outside_box: int = 0,
        blocked_shots: int = 0,
        total_shots: int = 0,
        matches_played: int = 1,
    ) -> dict:
        """
        Estima xG total y por partido a partir de datos de tiros.

        El modelo usa una combinación ponderada:
        1. xG por zona (dentro/fuera del área)
        2. xG por precisión (a puerta/bloqueados)
        3. Promedio de ambos para mayor robustez

        Returns:
            Dict con xg_total, xg_per_match, shot_quality, y desglose
        """
        if total_shots == 0 and shots_inside_box == 0:
            return {
                "xg_total": 0.0,
                "xg_per_match": 0.0,
                "shot_quality": 0.0,
                "method": "no_data",
            }

        # Método 1: xG por zona (más preciso si tenemos inside/outside)
        xg_zone = 0.0
        if shots_inside_box > 0 or shots_outside_box > 0:
            xg_zone = (
                shots_inside_box * XG_RATE_INSIDE_BOX +
                shots_outside_box * XG_RATE_OUTSIDE_BOX
            )

        # Método 2: xG por precisión
        xg_precision = 0.0
        if shots_on_goal > 0 or blocked_shots > 0:
            xg_precision = (
                shots_on_goal * XG_RATE_ON_TARGET +
                blocked_shots * XG_RATE_BLOCKED
            )

        # Combinar ambos métodos
        if xg_zone > 0 and xg_precision > 0:
            # Promedio ponderado: zona es más fiable
            xg_total = xg_zone * 0.6 + xg_precision * 0.4
        elif xg_zone > 0:
            xg_total = xg_zone
        elif xg_precision > 0:
            xg_total = xg_precision
        else:
            # Fallback: usar total_shots con tasa media
            avg_rate = (XG_RATE_INSIDE_BOX + XG_RATE_OUTSIDE_BOX) / 2
            xg_total = total_shots * avg_rate

        xg_per_match = xg_total / max(matches_played, 1)

        # Calidad de tiro (qué % de tiros son dentro del área)
        shot_quality = 0.0
        if total_shots > 0:
            inside = shots_inside_box if shots_inside_box > 0 else shots_on_goal
            shot_quality = inside / total_shots

        return {
            "xg_total": round(xg_total, 2),
            "xg_per_match": round(xg_per_match, 2),
            "shot_quality": round(shot_quality, 3),
            "shots_per_match": round(total_shots / max(matches_played, 1), 1),
            "method": "zone+precision" if xg_zone > 0 and xg_precision > 0 else "estimated",
        }

    @staticmethod
    def estimate_xg_against_from_stats(
        goalkeeper_saves: int = 0,
        shots_on_goal_against: int = 0,
        goals_against: int = 0,
        matches_played: int = 1,
    ) -> dict:
        """
        Estima xG en contra (xGA) — calidad defensiva.
        Usa saves del portero + goles encajados como proxy.
        """
        if goalkeeper_saves == 0 and goals_against == 0:
            return {"xga_per_match": 0.0, "save_rate": 0.0}

        # Total de tiros a puerta recibidos ≈ saves + goals conceded
        total_shots_faced = goalkeeper_saves + goals_against
        xga_total = total_shots_faced * XG_RATE_ON_TARGET
        xga_per_match = xga_total / max(matches_played, 1)

        save_rate = goalkeeper_saves / max(total_shots_faced, 1)

        return {
            "xga_per_match": round(xga_per_match, 2),
            "save_rate": round(save_rate, 3),
        }

    @staticmethod
    def blend_xg_with_goals(
        xg_per_match: float,
        goals_per_match: float,
        xg_weight: float = XG_WEIGHT,
    ) -> float:
        """
        Mezcla xG estimado con goles reales para el modelo Poisson.

        xG es mejor predictor que goles brutos pero puede tener error
        de estimación, así que mezclamos ambos.

        Args:
            xg_per_match: xG estimado por partido
            goals_per_match: Goles reales por partido
            xg_weight: Peso del xG (0-1). Default 0.65 (65% xG)

        Returns:
            Lambda ajustado para Poisson
        """
        if xg_per_match <= 0:
            return goals_per_match

        return xg_per_match * xg_weight + goals_per_match * (1 - xg_weight)
