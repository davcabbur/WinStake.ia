"""
WinStake.ia — Motor de Análisis Cuantitativo
Fachada que orquesta: PoissonModel/NormalModel, EVCalculator y MarketAnalyzer.

Todos los tipos se re-exportan aquí para mantener compatibilidad con
los imports existentes (main.py, database.py, formatter.py, etc.).
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

import config

# Re-exportar tipos para compatibilidad
from src.poisson_model import MatchProbabilities, PoissonModel
from src.normal_model import NBAMatchProbabilities, NormalModel
from src.ev_calculator import EVResult, KellyResult, EVCalculator
from src.market_analyzer import form_multiplier, h2h_adjustment, generate_insights

logger = logging.getLogger(__name__)


@dataclass
class MatchAnalysis:
    """Análisis completo de un partido (fútbol o basketball)."""
    home_team: str = ""
    away_team: str = ""
    commence_time: str = ""
    match_id: str = ""
    sport: str = "laliga"
    probabilities: object = field(default_factory=MatchProbabilities)
    market_odds: dict = field(default_factory=dict)
    ev_results: list = field(default_factory=list)
    best_bet: Optional[EVResult] = None
    kelly: Optional[KellyResult] = None
    confidence: str = "Baja"
    insights: list = field(default_factory=list)
    recommendation: str = "No apostar"
    correct_scores: list = field(default_factory=list)
    asian_handicap: dict = field(default_factory=dict)
    # Mercados fútbol
    corners: dict = field(default_factory=dict)
    cards: dict = field(default_factory=dict)
    scorers: dict = field(default_factory=dict)
    # Mercados NBA
    spread_lines: list = field(default_factory=list)
    total_lines: list = field(default_factory=list)
    player_props: dict = field(default_factory=dict)      # {"home": [...], "away": [...]}
    prop_recommendations: list = field(default_factory=list)  # lista de props recomendados
    team_last10: dict = field(default_factory=dict)       # {"home": [...], "away": [...]}
    injuries: dict = field(default_factory=dict)          # {"home": [...], "away": [...]}
    injury_alerts: list = field(default_factory=list)    # jugadores clave lesionados [{player, team, status, ppg}]
    blowout_context: object = None                        # BlowoutContext (NBA only)
    quarter_projections: list = field(default_factory=list)  # Q1-Q4 proyecciones (NBA only)
    stake_zero_overheat: bool = False                     # EV >40%: Stake 0u por Sabiduría de Mercado


class Analyzer:
    """
    Motor de análisis cuantitativo para apuestas deportivas.
    Soporta múltiples deportes mediante SportConfig.
    """

    def __init__(self, sport_config=None):
        # Sport config (default: La Liga para compatibilidad)
        self.sport_config = sport_config
        self.sport_key = sport_config.key if sport_config else "laliga"
        self.sport_type = sport_config.sport_type if sport_config else "football"

        self.home_advantage = sport_config.home_advantage if sport_config else config.HOME_ADVANTAGE
        self.form_weight = config.FORM_WEIGHT
        self.league_avg_goals = sport_config.league_avg_score if sport_config else config.LEAGUE_AVG_GOALS
        self.max_goals = sport_config.max_score_model if sport_config else config.MAX_GOALS_MODEL
        self.min_ev = config.MIN_EV_THRESHOLD
        self.kelly_cap = config.KELLY_CAP
        self.bankroll = config.BANKROLL_UNITS

        self._poisson = PoissonModel()
        if sport_config:
            self._poisson.home_advantage = sport_config.home_advantage
            self._poisson.league_avg_goals = sport_config.league_avg_score

        self._normal = NormalModel(sport_config=sport_config)
        self._ev_calc = EVCalculator()

    def calibrate_from_standings(self, standings: list[dict]) -> None:
        """Recalibra la media de goles/puntos de la liga desde datos reales."""
        if self.sport_type == "basketball":
            self._normal.update_league_avg_from_standings(standings)
        else:
            self._poisson.update_league_avg_from_standings(standings)

    def analyze_match(
        self,
        home_team: str,
        away_team: str,
        odds: dict,
        home_stats: Optional[dict] = None,
        away_stats: Optional[dict] = None,
        commence_time: str = "",
        h2h_data: Optional[list] = None,
        match_id: str = "",
        scorers: Optional[dict] = None,
    ) -> MatchAnalysis:
        """Análisis completo de un partido. Enruta al modelo correcto."""
        if self.sport_type == "basketball":
            return self._analyze_match_nba(
                home_team, away_team, odds, home_stats, away_stats,
                commence_time, h2h_data, match_id,
            )
        return self._analyze_match_football(
            home_team, away_team, odds, home_stats, away_stats,
            commence_time, h2h_data, match_id, scorers,
        )

    def _analyze_match_nba(
        self,
        home_team: str,
        away_team: str,
        odds: dict,
        home_stats: Optional[dict] = None,
        away_stats: Optional[dict] = None,
        commence_time: str = "",
        h2h_data: Optional[list] = None,
        match_id: str = "",
    ) -> MatchAnalysis:
        """Análisis completo de un partido NBA usando modelo Normal."""
        analysis = MatchAnalysis(
            home_team=home_team,
            away_team=away_team,
            commence_time=commence_time,
            match_id=match_id,
            market_odds=odds,
            sport=self.sport_key,
        )

        market_spread = odds.get("spread_line", 0.0) or 0.0
        market_total = odds.get("total_line", 0.0) or 0.0

        # 1. Predicción via modelo Normal
        probs = self._normal.predict(
            home_stats, away_stats,
            market_spread=market_spread,
            market_total=market_total,
            h2h_data=h2h_data,
        )
        analysis.probabilities = probs

        # 2. Calcular EV para mercados NBA
        ev_results = self._ev_calc.calculate_ev_nba(probs, odds)
        analysis.ev_results = ev_results

        # 3. Mejor apuesta
        best = self._ev_calc.find_best_bet(ev_results)

        # ── ML priority: spread de mercado >12.5 pts Y margen modelo >10 pts ──
        # Doble condición: si el mercado Y el modelo coinciden en que el partido
        # está muy desequilibrado, apostar el Spread es arriesgado (garbage time).
        # Se prefiere el ML si está disponible con cuota ≥ 1.25; si no, No Bet.
        _ML_PRIORITY_SPREAD_THRESHOLD = 12.5
        _ML_PRIORITY_MODEL_MARGIN = 10.0
        if best and best.selection in ("Spread Home", "Spread Away") and best.line is not None:
            if best.line < -_ML_PRIORITY_SPREAD_THRESHOLD and abs(probs.spread) > _ML_PRIORITY_MODEL_MARGIN:
                fav_ml_sel = "Home" if best.selection == "Spread Home" else "Away"
                fav_ml = next((r for r in ev_results if r.selection == fav_ml_sel), None)
                if fav_ml and fav_ml.odds >= 1.25:
                    logger.info(
                        f"ML priority ({home_team} vs {away_team}): "
                        f"{best.selection} line={best.line:.1f} → pivotando a ML {fav_ml_sel}"
                    )
                    best = fav_ml
                else:
                    # ML no disponible o cuota < 1.25 → No Bet
                    logger.info(
                        f"ML priority ({home_team} vs {away_team}): "
                        f"Spread>12 pts pero ML <1.25 → No Bet"
                    )
                    best = None

        analysis.best_bet = best

        # 4. Kelly criterion
        if best and best.is_value:
            kelly = self._ev_calc.kelly_criterion(best.probability, best.odds)
            analysis.kelly = kelly
            analysis.confidence = self._ev_calc.classify_confidence(best.ev_percent)
            analysis.recommendation = f"{best.selection} @ {best.odds:.2f}"
        else:
            analysis.recommendation = "No apostar"
            analysis.confidence = "—"

        # 5. Líneas de spread alternativas
        analysis.spread_lines = self._normal.spread_probabilities(
            probs.home_score, probs.away_score, probs.std_diff,
        )

        # 6. Líneas de totals alternativas
        std_total = (probs.std_home**2 + probs.std_away**2) ** 0.5
        analysis.total_lines = self._normal.total_probabilities(
            probs.total_score, std_total,
        )

        # 7. Insights NBA
        analysis.insights = self._generate_nba_insights(
            home_team, away_team, probs, odds, home_stats, away_stats, best, h2h_data,
        )

        # 8. Detección de correlación
        correlation_warnings = self._ev_calc.detect_correlated_bets_nba(ev_results)
        if correlation_warnings:
            analysis.insights.extend(correlation_warnings)

        return analysis

    @staticmethod
    def _team_motivation(win_pct: float) -> str:
        """Clasifica la motivación del equipo en abril por win_pct."""
        if win_pct is None:
            return "—"
        if win_pct >= 0.55:
            return "🏆 Contender"
        if win_pct >= 0.43:
            return "🎯 Play-in Hunter"
        if win_pct >= 0.35:
            return "🔒 Locked"
        return "💀 Tanking"

    def _generate_nba_insights(
        self,
        home_team: str,
        away_team: str,
        probs: NBAMatchProbabilities,
        odds: dict,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
        best_bet: Optional[EVResult],
        h2h_data: Optional[list] = None,
    ) -> list[str]:
        """Genera insights para partidos NBA."""
        insights = []

        insights.append(
            f"Score esperado: {home_team} {probs.home_score:.0f} — "
            f"{away_team} {probs.away_score:.0f} (Total: {probs.total_score:.0f})"
        )

        if probs.spread != 0:
            fav = home_team if probs.spread < 0 else away_team
            insights.append(f"Spread modelo: {fav} {abs(probs.spread):.1f} pts favorito")

        if home_stats and away_stats:
            # Diferencia de record
            home_wpct = home_stats.get("win_pct", 0)
            away_wpct = away_stats.get("win_pct", 0)
            if abs(home_wpct - away_wpct) > 0.200:
                better = home_team if home_wpct > away_wpct else away_team
                insights.append(f"{better} es claramente superior en record de temporada")

            # Clasificación motivacional + Filtro Abril
            home_mot = self._team_motivation(home_wpct)
            away_mot = self._team_motivation(away_wpct)
            insights.append(f"📅 Motivación: {home_team} {home_mot} | {away_team} {away_mot}")

            _PLAYOFF_CUTOFF = 0.40
            penalized = []
            if home_wpct is not None and home_wpct < _PLAYOFF_CUTOFF:
                penalized.append(f"{home_team} ({home_mot.split()[-1]}, win_pct {home_wpct:.0%})")
            if away_wpct is not None and away_wpct < _PLAYOFF_CUTOFF:
                penalized.append(f"{away_team} ({away_mot.split()[-1]}, win_pct {away_wpct:.0%})")
            if penalized:
                insights.append(
                    f"⚠️ Defensa −15% aplicada: {', '.join(penalized)} — total al alza"
                )

            # Pace
            home_pace = home_stats.get("pace", 100)
            away_pace = away_stats.get("pace", 100)
            avg_pace = (home_pace + away_pace) / 2
            if avg_pace > 101:
                insights.append(f"Partido de ritmo alto (pace ~{avg_pace:.0f}) — favorece Over")
            elif avg_pace < 97:
                insights.append(f"Partido de ritmo bajo (pace ~{avg_pace:.0f}) — favorece Under")

            # PPG vs opp
            home_ppg = home_stats.get("ppg", 112)
            away_opp = away_stats.get("opp_ppg", 112)
            if home_ppg > away_opp + 5:
                insights.append(f"{home_team} anota mas de lo que {away_team} permite — ventaja ofensiva")

        # Edge vs mercado
        if odds.get("home") and odds["home"] > 1.0:
            implied = 1 / odds["home"]
            edge = probs.home_win - implied
            if edge > 0.05:
                insights.append(f"{home_team} infravalorado por el mercado ({edge*100:.1f}% edge)")
            elif edge < -0.05:
                insights.append(f"{home_team} sobrevalorado por el mercado ({edge*100:.1f}%)")

        if not best_bet:
            insights.append("Sin edge: mercado bien calibrado para este partido")

        return insights

    def _analyze_match_football(
        self,
        home_team: str,
        away_team: str,
        odds: dict,
        home_stats: Optional[dict] = None,
        away_stats: Optional[dict] = None,
        commence_time: str = "",
        h2h_data: Optional[list] = None,
        match_id: str = "",
        scorers: Optional[dict] = None,
    ) -> MatchAnalysis:
        """Análisis completo de un partido de fútbol (modelo original)."""
        analysis = MatchAnalysis(
            home_team=home_team,
            away_team=away_team,
            commence_time=commence_time,
            match_id=match_id,
            market_odds=odds,
            sport=self.sport_key,
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

        # 10. Corners estimados
        analysis.corners = self._poisson.estimate_corners(
            probs.lambda_home, probs.lambda_away, home_stats, away_stats
        )

        # 11. Tarjetas estimadas
        is_derby = self._is_derby(home_team, away_team)
        analysis.cards = self._poisson.estimate_cards(
            probs.lambda_home, probs.lambda_away, home_stats, away_stats, is_derby
        )

        # 12. Goleadores
        if scorers:
            import math
            for side in ("home", "away"):
                for p in scorers.get(side, []):
                    # P(anotar) = 1 - e^(-goals_per_90)
                    p["anytime_scorer_prob"] = round(1 - math.exp(-p["goals_per_90"]), 4)
                    p["anytime_assist_prob"] = round(1 - math.exp(-p["assists_per_90"]), 4)
            analysis.scorers = scorers

        return analysis

    @staticmethod
    def _is_derby(home: str, away: str) -> bool:
        """Detecta si es un derby/clásico con mayor intensidad."""
        derbies = [
            ("real madrid", "barcelona"),
            ("real madrid", "atlético madrid"),
            ("barcelona", "atlético madrid"),
            ("real betis", "sevilla"),
            ("valencia", "levante"),
            ("athletic club", "real sociedad"),
            ("rayo vallecano", "getafe"),
            ("espanyol", "barcelona"),
            ("celta vigo", "deportivo"),
        ]
        h = home.lower()
        a = away.lower()
        for team_a, team_b in derbies:
            # Substring match: "Atlético Madrid" contiene "atlético madrid"
            home_is_a = team_a in h or h in team_a
            home_is_b = team_b in h or h in team_b
            away_is_a = team_a in a or a in team_a
            away_is_b = team_b in a or a in team_b
            if (home_is_a and away_is_b) or (home_is_b and away_is_a):
                return True
        return False

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
