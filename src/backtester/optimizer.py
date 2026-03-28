"""
WinStake.ia — Backtester Optimizer
Utiliza fuerza bruta (Grid Search) o algoritmia para probar parámetros de rentabilidad.
"""

import logging
from src.backtester.data_loader import DataLoader
from src.backtester.engine import BacktestEngine

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def run_grid_search(league="soccer_spain_la_liga", season_year=23):
    loader = DataLoader()
    filepath = loader.fetch_season_data(league, season_year)
    matches = loader.load_matches(filepath)
    
    # Parámetros a probar
    min_ev_range = [3.0, 5.0, 8.0, 10.0]
    wait_match_range = [5, 8, 12]
    
    logger.info("==============================================")
    logger.info(f"🎾 Iniciando Optimizador para Temporada {season_year}")
    logger.info("==============================================\n")
    
    results = []
    
    for wait in wait_match_range:
        for ev in min_ev_range:
            engine = BacktestEngine(min_matches_before_bet=wait)
            # Desactivamos logs verbose del engine temporalmente
            logging.getLogger("src.backtester.engine").setLevel(logging.WARNING)
            
            res = engine.run_season(matches, min_ev=ev)
            
            results.append({
                "Wait Matches": wait,
                "Min EV %": ev,
                "ROI %": res["roi"],
                "Bets": res["total_bets"],
                "Bankroll": res["bankroll"]
            })
            
            logger.info(f"Wait: {wait} | Min EV: {ev}% ---> ROI: {res['roi']:+.2f}% (Bets: {res['total_bets']})")

    logger.info("\n🏆 TOP PARAMETERS:")
    results.sort(key=lambda x: x["ROI %"], reverse=True)
    for r in results[:3]:
        logger.info(f"Wait {r['Wait Matches']} Jords | Min EV > {r['Min EV %']}  --> ROI: {r['ROI %']:+.2f}%")

if __name__ == "__main__":
    run_grid_search()
