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
    # Nuevos mercados
    double_chance_1x: float = 0.0
    double_chance_x2: float = 0.0
    double_chance_12: float = 0.0
    over_15: float = 0.0
    under_15: float = 0.0
    over_35: float = 0.0
    under_35: float = 0.0
    # Corners (estimación)
    corners_lambda_home: float = 0.0
    corners_lambda_away: float = 0.0
    corners_over_85: float = 0.0
    corners_over_95: float = 0.0
    corners_over_105: float = 0.0
    # Tarjetas (estimación)
    cards_lambda: float = 0.0
    cards_over_35: float = 0.0
    cards_over_45: float = 0.0
    cards_over_55: float = 0.0


class PoissonModel:
    """Modelo Poisson para predicción de goles en fútbol."""

    def __init__(self):
        self.home_advantage = config.HOME_ADVANTAGE
        self.form_weight = config.FORM_WEIGHT
        self.league_avg_goals = config.LEAGUE_AVG_GOALS
        self.max_goals = config.MAX_GOALS_MODEL

    def update_league_avg_from_standings(self, standings: list[dict]) -> None:
        """
        Recalcula LEAGUE_AVG_GOALS desde los datos reales de la clasificación.
        Más preciso que un hardcode estático.
        """
        if not standings:
            return
        total_goals = sum(t.get("goals_for", 0) for t in standings)
        total_played = sum(t.get("played", 0) for t in standings)
        if total_played > 0:
            # Cada partido tiene 2 equipos, así que total_goals ya es la suma de GF de todos
            # pero cada gol se cuenta dos veces (GF de un equipo = GA de otro)
            # total_matches = total_played / 2
            total_matches = total_played / 2
            real_avg = total_goals / total_matches
            if 1.5 < real_avg < 4.0:  # Sanity check
                old = self.league_avg_goals
                self.league_avg_goals = round(real_avg, 2)
                if abs(old - real_avg) > 0.1:
                    logger.info(
                        f"📊 LEAGUE_AVG_GOALS actualizado: {old} → {self.league_avg_goals} "
                        f"(calculado de {len(standings)} equipos, {int(total_matches)} partidos)"
                    )

    def dynamic_form_weight(self, matches_played: int) -> float:
        """
        Reduce el peso de la forma reciente conforme avanza la temporada.
        Con pocas jornadas, la forma reciente es más relevante.
        Con muchas jornadas, los datos de temporada son más robustos.

        J5: form_weight ≈ 0.35 (forma importa mucho)
        J15: form_weight ≈ 0.25 (equilibrado)
        J30: form_weight ≈ 0.15 (temporada domina)
        """
        if matches_played <= 0:
            return self.form_weight
        # Decae linealmente: base_weight * (1 - played/50)
        decay = max(0.10, self.form_weight * (1 - matches_played / 50))
        return round(decay, 3)

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
                # Form weight dinámico: menos peso a la forma con más partidos jugados
                dyn_fw = self.dynamic_form_weight(home_played)
                if "home" in home_stats and home_stats["home"]["played"] > 0:
                    home_home_gf = home_stats["home"]["goals_for"] / home_stats["home"]["played"]
                    lambda_home = lambda_home * (1 - dyn_fw) + home_home_gf * dyn_fw

                if "away" in away_stats and away_stats["away"]["played"] > 0:
                    away_away_gf = away_stats["away"]["goals_for"] / away_stats["away"]["played"]
                    lambda_away = lambda_away * (1 - dyn_fw) + away_away_gf * dyn_fw

        else:
            lambda_home = avg_goals_per_team * (1 + self.home_advantage)
            lambda_away = avg_goals_per_team * (1 - self.home_advantage * 0.5)

        lambda_home = max(0.3, min(4.0, lambda_home))
        lambda_away = max(0.2, min(3.5, lambda_away))

        # Ajuste por Forma Reciente (atenuado según jornada)
        if home_stats and away_stats and form_multiplier_fn:
            home_form_mult = form_multiplier_fn(home_stats.get("form", ""))
            away_form_mult = form_multiplier_fn(away_stats.get("form", ""))
            # Atenuar el efecto con más partidos jugados (regresión a la media)
            played = home_stats.get("played", 29) or 29
            attenuation = max(0.4, 1.0 - played / 50)  # J10: 0.8, J25: 0.5, J38: 0.4
            home_form_mult = 1.0 + (home_form_mult - 1.0) * attenuation
            away_form_mult = 1.0 + (away_form_mult - 1.0) * attenuation
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
        over_15 = 0.0
        over_25 = 0.0
        over_35 = 0.0
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

                total_goals = h + a
                if total_goals > 1:
                    over_15 += p
                if total_goals > 2:
                    over_25 += p
                if total_goals > 3:
                    over_35 += p

                if h > 0 and a > 0:
                    btts_yes += p

        total_1x2 = home_win + draw + away_win
        if total_1x2 > 0:
            home_win /= total_1x2
            draw /= total_1x2
            away_win /= total_1x2

        under_15 = 1.0 - over_15
        under_25 = 1.0 - over_25
        under_35 = 1.0 - over_35
        btts_no = 1.0 - btts_yes

        # Doble oportunidad
        dc_1x = home_win + draw
        dc_x2 = draw + away_win
        dc_12 = home_win + away_win

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
            double_chance_1x=round(dc_1x, 4),
            double_chance_x2=round(dc_x2, 4),
            double_chance_12=round(dc_12, 4),
            over_15=round(over_15, 4),
            under_15=round(under_15, 4),
            over_35=round(over_35, 4),
            under_35=round(under_35, 4),
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

    def estimate_corners(
        self,
        lambda_home: float,
        lambda_away: float,
        home_stats: Optional[dict] = None,
        away_stats: Optional[dict] = None,
    ) -> dict:
        """
        Estima corners usando correlación con fuerza de ataque.
        La Liga avg ~10 corners/partido. Equipos más atacantes generan más corners.
        """
        LA_LIGA_AVG_CORNERS = 10.0
        avg_goals_per_team = self.league_avg_goals / 2

        # Estimar corners por equipo basándose en su lambda ofensivo
        attack_ratio_home = lambda_home / avg_goals_per_team
        attack_ratio_away = lambda_away / avg_goals_per_team

        # Corners correlacionan con ataque: ~5 corners base por equipo
        corners_home = 5.0 * (0.6 + 0.4 * attack_ratio_home)
        corners_away = 5.0 * (0.6 + 0.4 * attack_ratio_away)

        # Ventaja local en corners
        corners_home *= 1.10
        corners_away *= 0.92

        total_corners = corners_home + corners_away

        # Usar Poisson para over/under
        over_85 = 1.0 - poisson.cdf(8, total_corners)
        over_95 = 1.0 - poisson.cdf(9, total_corners)
        over_105 = 1.0 - poisson.cdf(10, total_corners)

        return {
            "corners_home": round(corners_home, 1),
            "corners_away": round(corners_away, 1),
            "total": round(total_corners, 1),
            "over_85": round(over_85, 4),
            "over_95": round(over_95, 4),
            "over_105": round(over_105, 4),
        }

    def estimate_cards(
        self,
        lambda_home: float,
        lambda_away: float,
        home_stats: Optional[dict] = None,
        away_stats: Optional[dict] = None,
        is_derby: bool = False,
    ) -> dict:
        """
        Estima tarjetas usando correlación con estilo defensivo.
        La Liga avg ~4.5 tarjetas/partido.
        """
        LA_LIGA_AVG_CARDS = 4.5
        avg_goals_per_team = self.league_avg_goals / 2

        # Equipos más defensivos (menos goles a favor) tienden a cometer más faltas
        defense_factor_home = 1.0
        defense_factor_away = 1.0

        if home_stats and home_stats.get("played", 0) > 0:
            gf_ratio = home_stats["goals_for"] / home_stats["played"] / avg_goals_per_team
            defense_factor_home = max(0.7, min(1.4, 1.3 - 0.3 * gf_ratio))

        if away_stats and away_stats.get("played", 0) > 0:
            gf_ratio = away_stats["goals_for"] / away_stats["played"] / avg_goals_per_team
            defense_factor_away = max(0.7, min(1.4, 1.3 - 0.3 * gf_ratio))

        # Visitante recibe más tarjetas
        cards_home = (LA_LIGA_AVG_CARDS / 2) * 0.90 * defense_factor_home
        cards_away = (LA_LIGA_AVG_CARDS / 2) * 1.10 * defense_factor_away

        # Factor derby/rivalidad
        if is_derby:
            cards_home *= 1.20
            cards_away *= 1.20

        total_cards = cards_home + cards_away

        over_35 = 1.0 - poisson.cdf(3, total_cards)
        over_45 = 1.0 - poisson.cdf(4, total_cards)
        over_55 = 1.0 - poisson.cdf(5, total_cards)

        return {
            "cards_home": round(cards_home, 1),
            "cards_away": round(cards_away, 1),
            "total": round(total_cards, 1),
            "over_35": round(over_35, 4),
            "over_45": round(over_45, 4),
            "over_55": round(over_55, 4),
        }

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
