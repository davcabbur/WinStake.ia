"""
WinStake.ia — Modelo Normal (Basketball)
Calcula distribución de probabilidades de puntos usando distribución Normal.

En basketball (NBA), los scores son lo suficientemente altos (~112 pts/equipo)
para que la distribución Normal sea una buena aproximación.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from scipy.stats import norm

logger = logging.getLogger(__name__)


@dataclass
class NBAMatchProbabilities:
    """Probabilidades estimadas para un partido NBA."""
    home_win: float = 0.0
    away_win: float = 0.0
    draw: float = 0.0  # Siempre 0 en NBA (overtime)

    # Puntos esperados
    home_score: float = 0.0
    away_score: float = 0.0
    total_score: float = 0.0

    # Spread (diferencia esperada)
    spread: float = 0.0  # Negativo = home favorito

    # Totals (Over/Under)
    over_total: float = 0.0   # Prob de Over en la línea de referencia
    under_total: float = 0.0
    total_line: float = 0.0   # Línea de referencia (ej: 224.5)

    # Spreads probabilidades
    home_cover_prob: float = 0.0  # Prob de que home cubra el spread de mercado
    away_cover_prob: float = 0.0

    # Spread y total de mercado (para EV)
    market_spread: float = 0.0
    market_total: float = 0.0

    # Volatilidad
    std_home: float = 0.0
    std_away: float = 0.0
    std_diff: float = 0.0  # Desviación estándar de la diferencia


class NormalModel:
    """Modelo de distribución Normal para predicción de puntos NBA."""

    # Constantes NBA 2024-25
    LEAGUE_AVG_TOTAL = 224.0    # Puntos totales por partido
    HOME_ADVANTAGE = 3.0        # Puntos de ventaja local
    TEAM_STD_DEV = 12.0         # Desviación típica de puntos por equipo
    PACE_FACTOR_WEIGHT = 0.3    # Peso del ritmo de juego

    def __init__(self, sport_config=None):
        if sport_config:
            self.league_avg_total = sport_config.league_avg_score
            self.home_advantage = sport_config.home_advantage
        else:
            self.league_avg_total = self.LEAGUE_AVG_TOTAL
            self.home_advantage = self.HOME_ADVANTAGE / self.LEAGUE_AVG_TOTAL

        self.team_std_dev = self.TEAM_STD_DEV

    def update_league_avg_from_standings(self, standings: list[dict]) -> None:
        """Recalibra la media de puntos de la liga desde datos reales."""
        if not standings:
            return
        total_points = sum(t.get("points_for", 0) for t in standings)
        total_played = sum(t.get("played", 0) for t in standings)
        if total_played > 0:
            total_matches = total_played / 2
            real_avg = total_points / total_matches
            if 200 < real_avg < 250:  # Sanity check NBA
                old = self.league_avg_total
                self.league_avg_total = round(real_avg, 1)
                if abs(old - real_avg) > 2.0:
                    logger.info(
                        f"  LEAGUE_AVG_TOTAL actualizado: {old} -> {self.league_avg_total} "
                        f"(calculado de {len(standings)} equipos, {int(total_matches)} partidos)"
                    )

    def calculate_expected_scores(
        self,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
    ) -> tuple[float, float, float, float]:
        """
        Calcula puntos esperados para cada equipo.

        Usa factores ofensivos y defensivos relativos a la media de la liga,
        ajustados por ritmo de juego (pace) y ventaja local.

        Returns:
            (home_score, away_score, std_home, std_away)
        """
        avg_ppg = self.league_avg_total / 2  # ~112 pts/equipo

        if home_stats and away_stats:
            home_played = home_stats.get("played", 82) or 82
            away_played = away_stats.get("played", 82) or 82

            # PPG y OPP_PPG reales de cada equipo
            home_ppg = home_stats.get("ppg", 0) or (home_stats.get("points_for", 0) / home_played)
            home_opp_ppg = home_stats.get("opp_ppg", 0) or (home_stats.get("points_against", 0) / home_played)
            away_ppg = away_stats.get("ppg", 0) or (away_stats.get("points_for", 0) / away_played)
            away_opp_ppg = away_stats.get("opp_ppg", 0) or (away_stats.get("points_against", 0) / away_played)

            # Factores ofensivos y defensivos relativos a la media de la liga
            avg_ppg = self.league_avg_total / 2
            home_off = home_ppg / avg_ppg
            home_def = home_opp_ppg / avg_ppg
            away_off = away_ppg / avg_ppg
            away_def = away_opp_ppg / avg_ppg

            # ── Regresión a la media para equipos muy malos ──────
            # Equipos con win_pct < 0.28 (≈ peores 8-10 de la liga) tienden
            # a estar en modo "tanking" al final de temporada: rotaciones
            # cortas, sin motivación, jugadores de G-League. Sus stats de
            # temporada sobreestiman su nivel real en estos partidos.
            # Regresamos sus factores un 30% hacia 1.0 (media de liga).
            def _regression(factor: float, win_pct: float) -> float:
                if win_pct is None or win_pct >= 0.28:
                    return factor
                # Intensidad de regresión: 0% en win_pct=0.28 → 30% en win_pct=0.00
                strength = min(0.30, (0.28 - win_pct) / 0.28 * 0.30)
                return factor + strength * (1.0 - factor)

            home_win_pct = home_stats.get("win_pct")
            away_win_pct = away_stats.get("win_pct")
            home_off = _regression(home_off, home_win_pct)
            home_def = _regression(home_def, home_win_pct)
            away_off = _regression(away_off, away_win_pct)
            away_def = _regression(away_def, away_win_pct)

            # ── Filtro de Volatilidad "Abril" (End of Season) ────────
            # Equipos eliminados de playoffs (win_pct < 0.40) carecen de
            # incentivo defensivo en las últimas semanas de temporada.
            # Su defensa real permite ~15% más que sus stats históricas sugieren.
            # → Multiplicamos el factor defensivo del equipo que está eliminado.
            _PLAYOFF_WIN_PCT_CUTOFF  = 0.40
            _APRIL_DEFENSE_INFLATOR = 1.15  # +15% puntos permitidos

            if home_win_pct is not None and home_win_pct < _PLAYOFF_WIN_PCT_CUTOFF:
                home_def *= _APRIL_DEFENSE_INFLATOR
                logger.debug(
                    f"Filtro Abril: {home_stats.get('team', 'home')} "
                    f"(win_pct={home_win_pct:.2f}) — home_def ×{_APRIL_DEFENSE_INFLATOR}"
                )
            if away_win_pct is not None and away_win_pct < _PLAYOFF_WIN_PCT_CUTOFF:
                away_def *= _APRIL_DEFENSE_INFLATOR
                logger.debug(
                    f"Filtro Abril: {away_stats.get('team', 'away')} "
                    f"(win_pct={away_win_pct:.2f}) — away_def ×{_APRIL_DEFENSE_INFLATOR}"
                )

            # Puntos esperados: ataque propio * defensa rival * media liga
            # Este approach multiplicativo captura mejor las diferencias reales
            home_expected = home_off * away_def * avg_ppg
            away_expected = away_off * home_def * avg_ppg

            # Ajuste por pace (ritmo de juego)
            home_pace = home_stats.get("pace", 100.0) / 100.0
            away_pace = away_stats.get("pace", 100.0) / 100.0
            pace_factor = (home_pace + away_pace) / 2
            pace_adj = 1.0 + (pace_factor - 1.0) * self.PACE_FACTOR_WEIGHT
            home_expected *= pace_adj
            away_expected *= pace_adj

            # Ventaja local (calculada dinámicamente)
            ha_points = self.home_advantage * avg_ppg
            home_expected += ha_points / 2
            away_expected -= ha_points / 2

            # Desviación estándar ajustada por consistencia del equipo
            home_std = self.team_std_dev * max(0.8, min(1.3,
                home_stats.get("std_dev_factor", 1.0)))
            away_std = self.team_std_dev * max(0.8, min(1.3,
                away_stats.get("std_dev_factor", 1.0)))
        else:
            home_expected = avg_ppg + self.home_advantage * self.league_avg_total
            away_expected = avg_ppg - self.home_advantage * self.league_avg_total * 0.5
            home_std = self.team_std_dev
            away_std = self.team_std_dev

        # Clamp a rangos razonables NBA
        home_expected = max(95, min(135, home_expected))
        away_expected = max(90, min(130, away_expected))

        return (
            round(home_expected, 1),
            round(away_expected, 1),
            round(home_std, 1),
            round(away_std, 1),
        )

    def predict(
        self,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
        market_spread: float = 0.0,
        market_total: float = 0.0,
        h2h_data: Optional[list] = None,
    ) -> NBAMatchProbabilities:
        """
        Genera predicción completa para un partido NBA.

        Args:
            home_stats: Stats del equipo local
            away_stats: Stats del visitante
            market_spread: Spread del mercado (negativo = home favorito)
            market_total: Línea de Over/Under del mercado
            h2h_data: Historial directo (opcional)
        """
        home_score, away_score, std_home, std_away = self.calculate_expected_scores(
            home_stats, away_stats
        )

        # Ajuste H2H (ligero en NBA, menos relevante que en fútbol)
        if h2h_data and len(h2h_data) >= 3:
            h2h_home_adj, h2h_away_adj = self._h2h_adjustment_nba(h2h_data)
            home_score *= h2h_home_adj
            away_score *= h2h_away_adj
            home_score = round(max(95, min(135, home_score)), 1)
            away_score = round(max(90, min(130, away_score)), 1)

        # Diferencia esperada y su desviación estándar
        diff = home_score - away_score  # Positivo = home favorito
        std_diff = (std_home**2 + std_away**2) ** 0.5

        # P(home win) — base del modelo de standings
        home_win_model = norm.sf(0, loc=diff, scale=std_diff)

        # ── Calibración con spread de mercado ──────────────────
        # El spread incorpora información que el modelo no tiene (lesiones,
        # descanso, forma reciente, motivación...). Cuanto mayor el spread,
        # más nos fiamos del mercado frente al modelo de standings.
        #
        # Fórmula empírica NBA: cada punto de spread ≈ 2.85% de prob de victoria
        #   P(home) ≈ 0.50 + |spread| × 0.0285   (desde el punto de vista del favorito)
        if market_spread != 0:
            # market_spread < 0 → home es favorito; > 0 → away es favorito
            spread_implied_home = 0.50 + (-market_spread) * 0.0285
            spread_implied_home = max(0.02, min(0.98, spread_implied_home))

            # Peso del mercado: sube de 0% (spread=0) a 90% (spread≥20 pts)
            market_weight = min(abs(market_spread) / 20.0, 0.90)

            home_win = (1.0 - market_weight) * home_win_model + market_weight * spread_implied_home
        else:
            home_win = home_win_model

        home_win = round(max(0.02, min(0.98, home_win)), 4)
        away_win = round(1.0 - home_win, 4)

        # Total esperado
        total = home_score + away_score
        total_line = market_total if market_total > 0 else round(total, 0) + 0.5
        std_total = (std_home**2 + std_away**2) ** 0.5
        over_prob = norm.sf(total_line, loc=total, scale=std_total)
        under_prob = 1.0 - over_prob

        # Spread del mercado
        if market_spread != 0:
            # P(home + spread > away) = P(diff > -spread)
            home_cover = norm.sf(-market_spread, loc=diff, scale=std_diff)
            away_cover = 1.0 - home_cover
        else:
            home_cover = 0.5
            away_cover = 0.5

        return NBAMatchProbabilities(
            home_win=round(home_win, 4),
            away_win=round(away_win, 4),
            draw=0.0,
            home_score=home_score,
            away_score=away_score,
            total_score=round(total, 1),
            spread=round(-diff, 1),  # Convención: negativo = home favorito
            over_total=round(over_prob, 4),
            under_total=round(under_prob, 4),
            total_line=total_line,
            home_cover_prob=round(home_cover, 4),
            away_cover_prob=round(away_cover, 4),
            market_spread=market_spread,
            market_total=market_total,
            std_home=std_home,
            std_away=std_away,
            std_diff=round(std_diff, 1),
        )

    @staticmethod
    def _h2h_adjustment_nba(h2h_data: list) -> tuple[float, float]:
        """
        Ajuste ligero por H2H en NBA.
        Menos impacto que en fútbol porque NBA tiene más partidos y menos varianza táctica.
        Max ajuste: +/-3%.
        """
        if not h2h_data or len(h2h_data) < 3:
            return 1.0, 1.0

        home_wins = sum(1 for m in h2h_data if m.get("home_winner") is True)
        away_wins = sum(1 for m in h2h_data if m.get("home_winner") is False)
        total = len(h2h_data)

        home_rate = home_wins / total
        away_rate = away_wins / total

        sample_factor = min(1.0, (total - 2) * 0.2 + 0.4)

        home_adj = 1.0 + (home_rate - away_rate) * 0.03 * sample_factor
        away_adj = 1.0 + (away_rate - home_rate) * 0.03 * sample_factor

        home_adj = max(0.97, min(1.03, home_adj))
        away_adj = max(0.97, min(1.03, away_adj))

        return round(home_adj, 4), round(away_adj, 4)

    def spread_probabilities(
        self,
        home_score: float,
        away_score: float,
        std_diff: float,
    ) -> list[dict]:
        """Calcula probabilidades para varias líneas de spread."""
        diff = home_score - away_score
        spreads = [-10.5, -7.5, -5.5, -3.5, -1.5, 1.5, 3.5, 5.5, 7.5, 10.5]
        result = []

        for spread in spreads:
            # spread negativo = home da puntos
            home_cover = norm.sf(-spread, loc=diff, scale=std_diff)
            result.append({
                "spread": spread,
                "label": f"{'Home' if spread <= 0 else 'Away'} {spread:+.1f}",
                "home_cover_prob": round(home_cover, 4),
                "away_cover_prob": round(1.0 - home_cover, 4),
                "home_cover_pct": round(home_cover * 100, 1),
                "away_cover_pct": round((1.0 - home_cover) * 100, 1),
            })

        return result

    def total_probabilities(
        self,
        total_expected: float,
        std_total: float,
    ) -> list[dict]:
        """Calcula probabilidades para varias líneas de totals."""
        lines = [210.5, 215.5, 220.5, 224.5, 228.5, 232.5, 238.5]
        result = []

        for line in lines:
            over = norm.sf(line, loc=total_expected, scale=std_total)
            result.append({
                "line": line,
                "over_prob": round(over, 4),
                "under_prob": round(1.0 - over, 4),
                "over_pct": round(over * 100, 1),
                "under_pct": round((1.0 - over) * 100, 1),
            })

        return result

    def quarter_projections(
        self,
        total_expected: float,
        std_total: float,
        blowout_ctx=None,
    ) -> list[dict]:
        """
        Proyecciones de puntos totales por cuarto (Q1-Q4).

        Distribución estándar NBA 2024-25:
          Q1: 26%   Q2: 26%   Q3: 25.5%   Q4: 22.5%  (suma = 100%)

        En blowouts confirmados (blowout_prob > 0.30), Q4 se reduce
        a 20% porque el favorito saca titulares antes del final.

        Desviación estándar por cuarto se escala como:
          σ_Q = σ_full × √(weight × 4)
        (mayor varianza relativa en períodos más cortos).

        Returns list of dicts: quarter, expected, std, over_line, over_pct, under_pct
        """
        # Pesos base por cuarto
        weights = {"Q1": 0.260, "Q2": 0.260, "Q3": 0.255, "Q4": 0.225}

        # En blowout proyectado, reducir Q4 y redistribuir levemente
        is_blowout = blowout_ctx is not None and getattr(blowout_ctx, "is_blowout", False)
        if is_blowout:
            blowout_prob = getattr(blowout_ctx, "blowout_prob", 0.30)
            # Q4 se reduce de 22.5% hasta 20% según la severidad del blowout
            q4_reduction = min(0.025, (blowout_prob - 0.30) / 0.40 * 0.025)
            weights["Q4"] = round(weights["Q4"] - q4_reduction, 4)
            # Redistribuir la reducción en Q1-Q3 para mantener suma ≈ 100%
            dist = q4_reduction / 3
            weights["Q1"] = round(weights["Q1"] + dist, 4)
            weights["Q2"] = round(weights["Q2"] + dist, 4)
            weights["Q3"] = round(weights["Q3"] + dist, 4)

        result = []
        for q, w in weights.items():
            q_expected = round(total_expected * w, 1)
            # Escalar σ para el cuarto: más varianza relativa en períodos cortos
            q_std = round(std_total * (w * 4) ** 0.5, 1)
            # Línea de O/U estándar de mercado para este cuarto (redondear a .5)
            q_line = round(q_expected * 2) / 2  # .0 o .5
            over = float(norm.sf(q_line, loc=q_expected, scale=q_std))
            result.append({
                "quarter":   q,
                "expected":  q_expected,
                "std":       q_std,
                "line":      q_line,
                "over_pct":  round(over * 100, 1),
                "under_pct": round((1.0 - over) * 100, 1),
                "blowout_q4": is_blowout and q == "Q4",
            })

        return result
