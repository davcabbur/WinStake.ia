"""
WinStake.ia — Backtester Engine
Simula apuestas históricas iterando sobre partidos pasados.
Soporta 1X2, Over/Under 2.5 y genera métricas detalladas.
"""

import logging
from dataclasses import dataclass, field
from src.analyzer import Analyzer
from src.backtester.data_loader import DataLoader

logger = logging.getLogger(__name__)


class TeamStatsTracker:
    """Rastrea estadísticas de los equipos a lo largo de la temporada simulada."""

    def __init__(self):
        self.teams = {}
        self.total_goals = 0
        self.total_matches = 0

    def get_stats(self, team_name: str) -> dict | None:
        """Devuelve un objeto compatible con lo que espera Analyzer."""
        if team_name not in self.teams:
            return None

        t = self.teams[team_name]
        matches = t["matches_played"]
        if matches == 0:
            return None

        return {
            "played": matches,
            "goals_for": t["goals_for"],
            "goals_against": t["goals_against"],
            "xg_for_per_match": (t["goals_for"] * 0.95) / matches,
            "xg_against_per_match": (t["goals_against"] * 1.05) / matches,
            "form": self.get_form(team_name),
            "home": {
                "played": max(1, t["home_played"]),
                "goals_for": t["home_gf"],
                "goals_against": t["home_gc"],
                "wins": t["home_wins"],
                "draws": t["home_draws"],
                "losses": t["home_played"] - t["home_wins"] - t["home_draws"],
            },
            "away": {
                "played": max(1, t["away_played"]),
                "goals_for": t["away_gf"],
                "goals_against": t["away_gc"],
                "wins": t["away_wins"],
                "draws": t["away_draws"],
                "losses": t["away_played"] - t["away_wins"] - t["away_draws"],
            },
        }

    def _init_team(self, name: str):
        if name not in self.teams:
            self.teams[name] = {
                "matches_played": 0,
                "goals_for": 0, "goals_against": 0,
                "home_played": 0, "home_gf": 0, "home_gc": 0,
                "home_wins": 0, "home_draws": 0,
                "away_played": 0, "away_gf": 0, "away_gc": 0,
                "away_wins": 0, "away_draws": 0,
                "form_queue": [],
            }

    def update(self, home: str, away: str, home_goals: int, away_goals: int):
        """Actualiza estadísticas tras un partido."""
        self._init_team(home)
        self._init_team(away)

        h, a = self.teams[home], self.teams[away]

        h["matches_played"] += 1
        h["goals_for"] += home_goals
        h["goals_against"] += away_goals
        h["home_played"] += 1
        h["home_gf"] += home_goals
        h["home_gc"] += away_goals

        a["matches_played"] += 1
        a["goals_for"] += away_goals
        a["goals_against"] += home_goals
        a["away_played"] += 1
        a["away_gf"] += away_goals
        a["away_gc"] += home_goals

        if home_goals > away_goals:
            h["form_queue"].append("W")
            a["form_queue"].append("L")
            h["home_wins"] += 1
        elif home_goals < away_goals:
            h["form_queue"].append("L")
            a["form_queue"].append("W")
            a["away_wins"] += 1
        else:
            h["form_queue"].append("D")
            a["form_queue"].append("D")
            h["home_draws"] += 1
            a["away_draws"] += 1

        h["form_queue"] = h["form_queue"][-5:]
        a["form_queue"] = a["form_queue"][-5:]

        self.total_goals += (home_goals + away_goals)
        self.total_matches += 1

    def get_form(self, team_name: str) -> str:
        if team_name in self.teams:
            return "".join(self.teams[team_name]["form_queue"])
        return ""


def _check_bet_won(selection: str, home_goals: int, away_goals: int) -> bool:
    """Evalúa si una apuesta fue ganadora."""
    sel = selection.lower()
    if sel == "local":
        return home_goals > away_goals
    elif sel == "empate":
        return home_goals == away_goals
    elif sel == "visitante":
        return home_goals < away_goals
    elif sel == "over 2.5":
        return (home_goals + away_goals) > 2
    elif sel == "under 2.5":
        return (home_goals + away_goals) < 3
    elif sel == "btts sí":
        return home_goals > 0 and away_goals > 0
    elif sel == "btts no":
        return home_goals == 0 or away_goals == 0
    return False


@dataclass
class BacktestResult:
    """Resultado completo del backtest."""
    initial_bankroll: float = 100.0
    final_bankroll: float = 100.0
    roi_percent: float = 0.0
    total_bets: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    max_drawdown: float = 0.0
    longest_losing_streak: int = 0
    avg_odds: float = 0.0
    avg_ev: float = 0.0
    profit_by_market: dict = field(default_factory=dict)
    bets_by_market: dict = field(default_factory=dict)
    # Para calibración
    predictions: list = field(default_factory=list)
    history: list = field(default_factory=list)
    bankroll_curve: list = field(default_factory=list)


class BacktestEngine:
    """Motor de backtesting con soporte completo de mercados."""

    def __init__(self, initial_bankroll: float = 100.0, min_matches_before_bet: int = 5):
        self.initial_bankroll = initial_bankroll
        self.bankroll = initial_bankroll
        self.min_matches = min_matches_before_bet
        self.tracker = TeamStatsTracker()
        self.analyzer = Analyzer()

        self._history = []
        self._predictions = []
        self._bankroll_curve = []
        self._peak_bankroll = initial_bankroll
        self._max_drawdown = 0.0
        self._current_losing_streak = 0
        self._longest_losing_streak = 0

    def run_season(
        self,
        matches: list[dict],
        min_ev: float = 3.0,
        custom_weights: dict | None = None,
    ) -> BacktestResult:
        """
        Ejecuta simulación cronológica sobre una temporada.

        Args:
            matches: Lista de partidos ordenados cronológicamente
            min_ev: EV mínimo (%) para considerar una apuesta
            custom_weights: Override de parámetros del modelo
        """
        logger.info(f"Iniciando backtest: {len(matches)} partidos, min_ev={min_ev}%")

        if custom_weights:
            if "HOME_ADVANTAGE" in custom_weights:
                self.analyzer.home_advantage = custom_weights["HOME_ADVANTAGE"]
                self.analyzer._poisson.home_advantage = custom_weights["HOME_ADVANTAGE"]

        original_min_ev = self.analyzer.min_ev
        self.analyzer.min_ev = min_ev
        self.analyzer._ev_calc.min_ev = min_ev / 100.0

        self._bankroll_curve.append(self.bankroll)

        for m in matches:
            home = m["home_team"]
            away = m["away_team"]
            odds = m["odds"]
            hg = m["home_goals"]
            ag = m["away_goals"]

            h_stats = self.tracker.get_stats(home)
            a_stats = self.tracker.get_stats(away)

            if (h_stats and h_stats["played"] >= self.min_matches and
                    a_stats and a_stats["played"] >= self.min_matches):

                # Actualizar media de goles de la liga
                if self.tracker.total_matches > 0:
                    self.analyzer.league_avg_goals = self.tracker.total_goals / self.tracker.total_matches
                    self.analyzer._poisson.league_avg_goals = self.analyzer.league_avg_goals

                # Generar Over/Under odds sintéticos si no están en el CSV
                if "over_25" not in odds:
                    total_goals_avg = self.tracker.total_goals / max(self.tracker.total_matches, 1)
                    if total_goals_avg > 2.5:
                        odds["over_25"] = 1.85
                        odds["under_25"] = 2.00
                    else:
                        odds["over_25"] = 2.00
                        odds["under_25"] = 1.85

                analysis = self.analyzer.analyze_match(
                    home_team=home,
                    away_team=away,
                    odds=odds,
                    home_stats=h_stats,
                    away_stats=a_stats,
                    commence_time=m.get("date", ""),
                )

                # Guardar predicción para calibración
                p = analysis.probabilities
                self._predictions.append({
                    "date": m.get("date", ""),
                    "home_team": home,
                    "away_team": away,
                    "prob_home": p.home_win,
                    "prob_draw": p.draw,
                    "prob_away": p.away_win,
                    "prob_over25": p.over_25,
                    "actual_result": m.get("result", ""),
                    "home_goals": hg,
                    "away_goals": ag,
                })

                # Simular apuesta si hay value
                if analysis.best_bet and analysis.best_bet.is_value:
                    self._simulate_bet(m, analysis)

            # Actualizar stats con resultado real
            self.tracker.update(home, away, hg, ag)

        # Restaurar
        self.analyzer.min_ev = original_min_ev
        self.analyzer._ev_calc.min_ev = original_min_ev

        return self._build_result()

    def _simulate_bet(self, match: dict, analysis):
        """Simula una apuesta y actualiza bankroll."""
        bet = analysis.best_bet
        kelly = analysis.kelly

        stake = min(kelly.stake_units if kelly else 1.0, self.bankroll)
        if stake <= 0:
            return

        hg = match["home_goals"]
        ag = match["away_goals"]
        won = _check_bet_won(bet.selection, hg, ag)

        if won:
            profit = round(stake * (bet.odds - 1), 2)
            self.bankroll += profit
            self._current_losing_streak = 0
        else:
            profit = -stake
            self.bankroll -= stake
            self._current_losing_streak += 1
            self._longest_losing_streak = max(
                self._longest_losing_streak, self._current_losing_streak
            )

        self.bankroll = round(self.bankroll, 2)

        # Drawdown
        if self.bankroll > self._peak_bankroll:
            self._peak_bankroll = self.bankroll
        dd = (self._peak_bankroll - self.bankroll) / self._peak_bankroll * 100
        self._max_drawdown = max(self._max_drawdown, dd)

        market = bet.selection
        self._history.append({
            "date": match.get("date", ""),
            "match": f"{match['home_team']} vs {match['away_team']}",
            "selection": market,
            "odds": bet.odds,
            "ev_percent": bet.ev_percent,
            "stake": stake,
            "profit": profit,
            "bankroll": self.bankroll,
            "won": won,
        })
        self._bankroll_curve.append(self.bankroll)

    def _build_result(self) -> BacktestResult:
        """Construye el resultado final del backtest."""
        total = len(self._history)
        wins = sum(1 for h in self._history if h["won"])
        losses = total - wins

        profit_by_market = {}
        bets_by_market = {}
        for h in self._history:
            mkt = h["selection"]
            profit_by_market[mkt] = profit_by_market.get(mkt, 0) + h["profit"]
            if mkt not in bets_by_market:
                bets_by_market[mkt] = {"total": 0, "wins": 0}
            bets_by_market[mkt]["total"] += 1
            if h["won"]:
                bets_by_market[mkt]["wins"] += 1

        avg_odds = sum(h["odds"] for h in self._history) / total if total else 0
        avg_ev = sum(h["ev_percent"] for h in self._history) / total if total else 0

        return BacktestResult(
            initial_bankroll=self.initial_bankroll,
            final_bankroll=self.bankroll,
            roi_percent=round((self.bankroll - self.initial_bankroll) / self.initial_bankroll * 100, 2),
            total_bets=total,
            wins=wins,
            losses=losses,
            win_rate=round(wins / total * 100, 2) if total else 0,
            max_drawdown=round(self._max_drawdown, 2),
            longest_losing_streak=self._longest_losing_streak,
            avg_odds=round(avg_odds, 2),
            avg_ev=round(avg_ev, 2),
            profit_by_market={k: round(v, 2) for k, v in profit_by_market.items()},
            bets_by_market=bets_by_market,
            predictions=self._predictions,
            history=self._history,
            bankroll_curve=self._bankroll_curve,
        )


def run_backtest(
    league: str = "soccer_spain_la_liga",
    season: int = 23,
    min_ev: float = 3.0,
    min_matches: int = 8,
    bankroll: float = 100.0,
) -> BacktestResult:
    """Función de conveniencia para ejecutar un backtest completo."""
    loader = DataLoader()
    filepath = loader.fetch_season_data(league, season)
    matches = loader.load_matches(filepath)

    engine = BacktestEngine(
        initial_bankroll=bankroll,
        min_matches_before_bet=min_matches,
    )
    return engine.run_season(matches, min_ev=min_ev)
