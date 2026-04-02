"""
WinStake.ia — Analizador de Mercado
Form multiplier, H2H adjustment e insights de mercado.
"""

import logging
from typing import Optional

from src.poisson_model import MatchProbabilities
from src.ev_calculator import EVResult

logger = logging.getLogger(__name__)

# Pesos temporales para form: el partido más reciente pesa más
# [más reciente → más antiguo]
FORM_DECAY_WEIGHTS = [1.0, 0.8, 0.6, 0.4, 0.2]

# Mínimo de partidos H2H para aplicar ajuste
H2H_MIN_MATCHES = 3


def form_multiplier(form: str) -> float:
    """
    Calcula multiplicador de lambda basado en forma reciente con decay temporal.

    Los partidos más recientes pesan más que los antiguos:
    weights = [1.0, 0.8, 0.6, 0.4, 0.2] (del más reciente al más antiguo)

    W=+2, D=0, L=-2. Resultado: multiplicador entre 0.90 y 1.10.
    """
    if not form:
        return 1.0

    recent = form[-5:].upper()
    if len(recent) < 3:
        return 1.0

    # Invertir para que el índice 0 sea el más reciente
    chars = list(reversed(recent))
    weights = FORM_DECAY_WEIGHTS[:len(chars)]

    weighted_score = 0.0
    total_weight = sum(weights)

    for i, char in enumerate(chars):
        if char == 'W':
            weighted_score += 2 * weights[i]
        elif char == 'L':
            weighted_score -= 2 * weights[i]
        # D = 0, no suma

    # Normalizar: max = 2 * total_weight, min = -2 * total_weight
    max_score = 2 * total_weight
    normalized = weighted_score / max_score  # -1.0 a 1.0
    multiplier = 1.0 + (normalized * 0.10)   # 0.90 a 1.10

    return round(multiplier, 3)


def h2h_adjustment(h2h_data: list) -> tuple[float, float]:
    """
    Calcula ajuste de lambda basado en historial directo (H2H).

    Requiere mínimo 3 partidos para significancia estadística.
    El ajuste se escala por sample size: con 3 partidos aplica 60%,
    con 5 partidos aplica 100% del ajuste calculado.

    Max ajuste: ±8%.

    Returns:
        (home_multiplier, away_multiplier)
    """
    if not h2h_data or len(h2h_data) < H2H_MIN_MATCHES:
        return 1.0, 1.0

    home_wins = 0
    away_wins = 0
    total_home_goals = 0
    total_away_goals = 0

    for match in h2h_data:
        hg = match.get("home_goals", 0) or 0
        ag = match.get("away_goals", 0) or 0
        total_home_goals += hg
        total_away_goals += ag

        if match.get("home_winner") is True:
            home_wins += 1
        elif match.get("home_winner") is False:
            away_wins += 1

    total = len(h2h_data)
    if total == 0:
        return 1.0, 1.0

    home_rate = home_wins / total
    away_rate = away_wins / total

    # Escalar por sample size: 3 partidos = 60%, 4 = 80%, 5+ = 100%
    sample_factor = min(1.0, (total - 2) * 0.2 + 0.4)  # 3→0.6, 4→0.8, 5→1.0

    home_adj = 1.0 + (home_rate - away_rate) * 0.08 * sample_factor
    away_adj = 1.0 + (away_rate - home_rate) * 0.08 * sample_factor

    home_adj = max(0.92, min(1.08, home_adj))
    away_adj = max(0.92, min(1.08, away_adj))

    return round(home_adj, 3), round(away_adj, 3)


def generate_insights(
    home_team: str,
    away_team: str,
    probs: MatchProbabilities,
    odds: dict,
    home_stats: Optional[dict],
    away_stats: Optional[dict],
    best_bet: Optional[EVResult],
    h2h_data: Optional[list] = None,
) -> list[str]:
    """Genera insights estilo Moneyball basados en datos."""
    insights = []

    total_lambda = probs.lambda_home + probs.lambda_away
    insights.append(
        f"Goles esperados: {home_team} {probs.lambda_home:.1f} — "
        f"{away_team} {probs.lambda_away:.1f} (Total: {total_lambda:.1f})"
    )

    if probs.xg_used:
        xg_diff_home = probs.xg_home - (home_stats["goals_for"] / max(home_stats["played"], 1)) if home_stats else 0
        if abs(xg_diff_home) > 0.3:
            if xg_diff_home > 0:
                insights.append(f"⚡ {home_team} rinde por debajo de su xG — mala suerte, debería mejorar")
            else:
                insights.append(f"🎯 {home_team} supera su xG — eficiencia goleadora alta")

    if home_stats and away_stats:
        home_form = home_stats.get("form", "")
        away_form = away_stats.get("form", "")
        if home_form:
            form_display = " ".join(home_form[-5:].upper())
            mult = form_multiplier(home_form)
            if mult >= 1.06:
                insights.append(f"🔥 {home_team} en racha: {form_display} (λ +{(mult-1)*100:.0f}%)")
            elif mult <= 0.94:
                insights.append(f"❌ {home_team} en mala racha: {form_display} (λ {(mult-1)*100:.0f}%)")

        if away_form:
            form_display = " ".join(away_form[-5:].upper())
            mult = form_multiplier(away_form)
            if mult >= 1.06:
                insights.append(f"🔥 {away_team} en racha: {form_display} (λ +{(mult-1)*100:.0f}%)")
            elif mult <= 0.94:
                insights.append(f"❌ {away_team} en mala racha: {form_display} (λ {(mult-1)*100:.0f}%)")

        if h2h_data and len(h2h_data) >= H2H_MIN_MATCHES:
            h2h_home_adj, h2h_away_adj = h2h_adjustment(h2h_data)
            if h2h_home_adj > 1.03:
                insights.append(f"🏆 {home_team} domina el H2H (últimos {len(h2h_data)} enfrentamientos)")
            elif h2h_away_adj > 1.03:
                insights.append(f"🏆 {away_team} domina el H2H (últimos {len(h2h_data)} enfrentamientos)")

        diff = home_stats.get("goal_diff", 0) - away_stats.get("goal_diff", 0)
        if abs(diff) > 20:
            better = home_team if diff > 0 else away_team
            insights.append(f"Diferencial de calidad muy alto: {better} es claramente superior (+{abs(diff)} GD)")

        if home_stats.get("draws", 0) >= 9:
            insights.append(f"{home_team} empata mucho ({home_stats['draws']} en {home_stats['played']} partidos)")
        if away_stats.get("draws", 0) >= 9:
            insights.append(f"{away_team} empata mucho ({away_stats['draws']} en {away_stats['played']} partidos)")

        home_gf_avg = home_stats["goals_for"] / max(home_stats["played"], 1)
        away_gf_avg = away_stats["goals_for"] / max(away_stats["played"], 1)
        if home_gf_avg < 1.0:
            insights.append(f"⚠️ {home_team} es muy poco goleador ({home_gf_avg:.1f} GF/partido)")
        if away_gf_avg < 1.0:
            insights.append(f"⚠️ {away_team} es muy poco goleador ({away_gf_avg:.1f} GF/partido)")

        if home_stats.get("rank", 20) >= 18:
            insights.append(f"🔴 {home_team} en zona de descenso — motivación máxima")
        elif home_stats.get("rank", 20) <= 4:
            insights.append(f"🟢 {home_team} en zona Champions — alta motivación")

        if away_stats.get("rank", 20) >= 18:
            insights.append(f"🔴 {away_team} en zona de descenso — motivación máxima")
        elif away_stats.get("rank", 20) <= 4:
            insights.append(f"🟢 {away_team} en zona Champions — alta motivación")

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
