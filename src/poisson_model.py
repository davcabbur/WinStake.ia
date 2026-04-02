"""
WinStake.ia — Modelo Poisson
Calcula distribución de probabilidades de goles usando Poisson.
"""

import logging
from dataclasses import dataclass
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
    xg_home: float = 0.0
    xg_away: float = 0.0
    xg_used: bool = False


class PoissonModel:
    """Modelo Poisson para predicción de goles en fútbol."""

    def __init__(self):
        self.home_advantage = config.HOME_ADVANTAGE
        self.form_weight = config.FORM_WEIGHT
        self.league_avg_goals = config.LEAGUE_AVG_GOALS
        self.max_goals = config.MAX_GOALS_MODEL

    def calculate_lambdas(
        self,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
        h2h_data: Optional[list] = None,
        form_multiplier_fn=None,
        h2h_adjustment_fn=None,
    ) -> tuple[float, float, float, float, bool]:
        """
        Calcula los parámetros λ (goles esperados) para cada equipo.

        Returns:
            (lambda_home, lambda_away, xg_home, xg_away, xg_used)
        """
        avg_goals_per_team = self.league_avg_goals / 2
        xg_home_val = 0.0
        xg_away_val = 0.0
        xg_used = False

        if home_stats and away_stats:
            home_played = home_stats.get("played", 29) or 29
            away_played = away_stats.get("played", 29) or 29

            home_attack = (home_stats["goals_for"] / home_played) / avg_goals_per_team
            home_defense = (home_stats["goals_against"] / home_played) / avg_goals_per_team
            away_attack = (away_stats["goals_for"] / away_played) / avg_goals_per_team
            away_defense = (away_stats["goals_against"] / away_played) / avg_goals_per_team

            lambda_home = home_attack * away_defense * avg_goals_per_team
            lambda_away = away_attack * home_defense * avg_goals_per_team

            lambda_home *= (1 + self.home_advantage)
            lambda_away *= (1 - self.home_advantage * 0.5)

            # xG Integration
            home_xg_pm = home_stats.get("xg_for_per_match", 0)
            away_xg_pm = away_stats.get("xg_for_per_match", 0)
            home_xga_pm = home_stats.get("xg_against_per_match", 0)
            away_xga_pm = away_stats.get("xg_against_per_match", 0)

            if home_xg_pm > 0 and away_xg_pm > 0:
                xg_used = True
                xg_home_val = home_xg_pm
                xg_away_val = away_xg_pm

                home_xg_attack = home_xg_pm / avg_goals_per_team
                away_xg_defense = away_xga_pm / avg_goals_per_team
                away_xg_attack = away_xg_pm / avg_goals_per_team
                home_xg_defense = home_xga_pm / avg_goals_per_team

                lambda_home_xg = home_xg_attack * away_xg_defense * avg_goals_per_team
                lambda_away_xg = away_xg_attack * home_xg_defense * avg_goals_per_team

                lambda_home_xg *= (1 + self.home_advantage)
                lambda_away_xg *= (1 - self.home_advantage * 0.5)

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
                if "home" in home_stats and home_stats["home"]["played"] > 0:
                    home_home_gf = home_stats["home"]["goals_for"] / home_stats["home"]["played"]
                    lambda_home = lambda_home * (1 - self.form_weight) + home_home_gf * self.form_weight

                if "away" in away_stats and away_stats["away"]["played"] > 0:
                    away_away_gf = away_stats["away"]["goals_for"] / away_stats["away"]["played"]
                    lambda_away = lambda_away * (1 - self.form_weight) + away_away_gf * self.form_weight

        else:
            lambda_home = avg_goals_per_team * (1 + self.home_advantage)
            lambda_away = avg_goals_per_team * (1 - self.home_advantage * 0.5)

        lambda_home = max(0.3, min(4.0, lambda_home))
        lambda_away = max(0.2, min(3.5, lambda_away))

        # Ajuste por Forma Reciente
        if home_stats and away_stats and form_multiplier_fn:
            home_form_mult = form_multiplier_fn(home_stats.get("form", ""))
            away_form_mult = form_multiplier_fn(away_stats.get("form", ""))
            if home_form_mult != 1.0 or away_form_mult != 1.0:
                lambda_home *= home_form_mult
                lambda_away *= away_form_mult
                lambda_home = max(0.3, min(4.0, lambda_home))
                lambda_away = max(0.2, min(3.5, lambda_away))

        # Ajuste por H2H
        if h2h_data and len(h2h_data) >= 3 and h2h_adjustment_fn:
            h2h_adj_home, h2h_adj_away = h2h_adjustment_fn(h2h_data)
            lambda_home *= h2h_adj_home
            lambda_away *= h2h_adj_away
            lambda_home = max(0.3, min(4.0, lambda_home))
            lambda_away = max(0.2, min(3.5, lambda_away))

        return round(lambda_home, 3), round(lambda_away, 3), round(xg_home_val, 2), round(xg_away_val, 2), xg_used

    def poisson_probabilities(
        self, lambda_home: float, lambda_away: float
    ) -> MatchProbabilities:
        """Genera distribución de probabilidades usando modelo Poisson."""
        home_win = 0.0
        draw = 0.0
        away_win = 0.0
        over_25 = 0.0
        btts_yes = 0.0

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

    def correct_score_matrix(
        self, lambda_home: float, lambda_away: float, top_n: int = 5
    ) -> list[dict]:
        """Genera la matriz de resultados exactos más probables."""
        scores = []
        for h in range(6):
            for a in range(6):
                prob = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
                scores.append({
                    "score": f"{h}-{a}",
                    "home_goals": h,
                    "away_goals": a,
                    "probability": round(prob, 4),
                    "percentage": round(prob * 100, 1),
                })

        scores.sort(key=lambda x: x["probability"], reverse=True)
        return scores[:top_n]

    def asian_handicap(
        self, lambda_home: float, lambda_away: float, odds: dict
    ) -> dict:
        """Calcula análisis de hándicap asiático."""
        handicaps = [-1.5, -1.0, -0.5, 0, +0.5, +1.0, +1.5]
        result = {"lines": [], "best_line": None}

        for hcap in handicaps:
            p_cover_home = 0.0
            p_cover_away = 0.0

            for h in range(self.max_goals + 1):
                for a in range(self.max_goals + 1):
                    p = poisson.pmf(h, lambda_home) * poisson.pmf(a, lambda_away)
                    margin = h - a
                    adjusted = margin + hcap
                    if adjusted > 0:
                        p_cover_home += p
                    elif adjusted < 0:
                        p_cover_away += p

            line_info = {
                "handicap": hcap,
                "label": f"{'Local' if hcap <= 0 else 'Visitante'} {hcap:+.1f}",
                "home_cover_prob": round(p_cover_home, 4),
                "away_cover_prob": round(p_cover_away, 4),
                "home_cover_pct": round(p_cover_home * 100, 1),
                "away_cover_pct": round(p_cover_away * 100, 1),
            }
            result["lines"].append(line_info)

            if not result["best_line"]:
                result["best_line"] = line_info
            else:
                curr_balance = abs(p_cover_home - 0.5)
                best_balance = abs(result["best_line"]["home_cover_prob"] - 0.5)
                if curr_balance < best_balance:
                    result["best_line"] = line_info

        return result
