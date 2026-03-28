"""
WinStake.ia — Backtester Engine
Simula apuestas históricas iterando sobre partidos pasados.
"""

import logging
from src.analyzer import Analyzer
from src.backtester.data_loader import DataLoader

logger = logging.getLogger(__name__)

class TeamStatsTracker:
    """Rastrea estadísticas de los equipos a lo largo de la temporada simulada."""
    def __init__(self):
        self.teams = {}
        self.total_goals = 0
        self.total_matches = 0

    def get_stats(self, team_name: str) -> dict:
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
            "form": "D" * min(5, matches),
            # Mock home/away inner dicts to avoid KeyErrors in non-xg fallback logic
            "home": {"played": matches/2, "goals_for": t["goals_for"]/2},
            "away": {"played": matches/2, "goals_for": t["goals_for"]/2}
        }

    def _init_team(self, name: str):
        if name not in self.teams:
            self.teams[name] = {
                "matches_played": 0,
                "goals_for": 0,
                "goals_against": 0,
                "form_queue": [] # Podríamos trackear W/D/L
            }

    def update(self, home: str, away: str, home_goals: int, away_goals: int, 
               home_xg: float = None, away_xg: float = None):
        """Actualiza la 'clasificación' tras un partido."""
        self._init_team(home)
        self._init_team(away)
        
        self.teams[home]["matches_played"] += 1
        self.teams[home]["goals_for"] += home_goals
        self.teams[home]["goals_against"] += away_goals
        
        self.teams[away]["matches_played"] += 1
        self.teams[away]["goals_for"] += away_goals
        self.teams[away]["goals_against"] += home_goals
        
        # Guardar forma
        if home_goals > away_goals:
            self.teams[home]["form_queue"].append("W")
            self.teams[away]["form_queue"].append("L")
        elif home_goals < away_goals:
            self.teams[home]["form_queue"].append("L")
            self.teams[away]["form_queue"].append("W")
        else:
            self.teams[home]["form_queue"].append("D")
            self.teams[away]["form_queue"].append("D")
            
        # Mantener solo ultimos 5
        self.teams[home]["form_queue"] = self.teams[home]["form_queue"][-5:]
        self.teams[away]["form_queue"] = self.teams[away]["form_queue"][-5:]
        
        self.total_goals += (home_goals + away_goals)
        self.total_matches += 1

    def get_form(self, team_name: str) -> str:
        if team_name in self.teams:
            return "".join(reversed(self.teams[team_name]["form_queue"]))
        return ""


class BacktestEngine:
    def __init__(self, initial_bankroll: float = 100.0, min_matches_before_bet: int = 5):
        self.bankroll = initial_bankroll
        self.min_matches = min_matches_before_bet
        self.tracker = TeamStatsTracker()
        self.analyzer = Analyzer()
        
        # Resultados
        self.history = []
        self.total_bets = 0
        self.wins = 0
        self.losses = 0
        
    def run_season(self, matches: list[dict], min_ev: float = 3.0, custom_weights: dict = None):
        """
        Ejecuta la simulación cronológica.
        custom_weights permite sobrescribir (para el optimizer).
        """
        logger.info(f"🚀 Iniciando backtest con {len(matches)} partidos.")
        
        if custom_weights:
            # Injectar overrides en Analyzer si es necesario
            if "HOME_ADVANTAGE" in custom_weights:
                self.analyzer.home_advantage = custom_weights["HOME_ADVANTAGE"]
            if "MIN_EV" in custom_weights:
                self.analyzer.min_ev = custom_weights["MIN_EV"]
        
        # Override EV mínimo temporal
        original_min_ev = self.analyzer.min_ev
        self.analyzer.min_ev = min_ev

        for m in matches:
            home = m["home_team"]
            away = m["away_team"]
            odds = m["odds"]
            
            h_stats = self.tracker.get_stats(home)
            a_stats = self.tracker.get_stats(away)
            
            if h_stats and a_stats:
                pass

            if h_stats and h_stats["played"] >= self.min_matches and \
               a_stats and a_stats["played"] >= self.min_matches:
                   
                # Update form string in stats
                h_stats["form"] = self.tracker.get_form(home)
                a_stats["form"] = self.tracker.get_form(away)
                
                # Actualizar promedio liga en analyzer
                avg_goals_match = self.tracker.total_goals / self.tracker.total_matches if self.tracker.total_matches > 0 else 2.5
                self.analyzer.league_avg_goals = avg_goals_match

                # Analizar
                analysis = self.analyzer.analyze_match(
                    home_team=home,
                    away_team=away,
                    odds=odds,
                    home_stats=h_stats,
                    away_stats=a_stats,
                    commence_time=m["date"]
                )
                
                if analysis.best_bet and analysis.best_bet.is_value:
                    self._simulate_bet(m, analysis)

            # Tras el partido o análisis, actualizamos las estadísticas reales con el resultado
            self.tracker.update(home, away, m["home_goals"], m["away_goals"])

        # Retornar estado normal
        self.analyzer.min_ev = original_min_ev

        roi = (self.bankroll - 100.0) / 100.0 * 100
        logger.info(f"🏁 Backtest finalizado. Apuestas: {self.total_bets} | Wins: {self.wins} | Bank final: {self.bankroll:.2f}U | ROI: {roi:.2f}%")
        
        return {
            "bankroll": self.bankroll,
            "roi": roi,
            "total_bets": self.total_bets,
            "wins": self.wins,
            "losses": self.losses,
            "history": self.history
        }

    def _simulate_bet(self, real_match: dict, analysis):
        """Evalúa si la apuesta fue ganadora cruzando la selección con el FTR (Full Time Result)."""
        bet = analysis.best_bet
        kelly = analysis.kelly
        
        # Stake (si baja de 0 el bankroll, truncamos)
        stake = min(kelly.stake_units if kelly else 1.0, self.bankroll)
        print(f'KELLY: {kelly}, STAKE: {stake}')
        if stake <= 0:
            print('BANCARROTA')
            return  # Bancarrota
            
        self.total_bets += 1
        
        # Traducir resultado real
        rt = real_match["result"] # H, D, A
        is_won = False
        if bet.selection == "Local" and rt == "H": is_won = True
        elif bet.selection == "Empate" and rt == "D": is_won = True
        elif bet.selection == "Visitante" and rt == "A": is_won = True
        # En the future: add logic for BTTS and O/U reading real goals from CSV
        
        if is_won:
            profit = stake * (bet.odds - 1)
            self.bankroll += profit
            self.wins += 1
            status = "WON"
        else:
            profit = -stake
            self.bankroll -= stake
            self.losses += 1
            status = "LOST"
            
        self.history.append({
            "date": real_match["date"],
            "match": f"{real_match['home_team']} vs {real_match['away_team']}",
            "selection": bet.selection,
            "odds": bet.odds,
            "ev": bet.ev_percent,
            "stake": stake,
            "profit": profit,
            "bankroll": self.bankroll,
            "status": status
        })

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = DataLoader()
    # Descargar ultima temporada de liga española (23 -> 2023/24)
    filepath = loader.fetch_season_data("soccer_spain_la_liga", 23)
    
    matches = loader.load_matches(filepath)
    engine = BacktestEngine(min_matches_before_bet=8) # Esperar a la jornada 8
    
    res = engine.run_season(matches, min_ev=3.0) 
