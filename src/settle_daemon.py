"""
WinStake.ia — Settle Daemon
Liquida value bets pendientes (LaLiga + NBA) cada 60 min dentro de la
ventana activa 10:00–02:00. Diseñado para correr como proceso PM2
(winstake-settle).
"""

import os
import sys
import time
from datetime import datetime

import schedule

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.logger_config import setup_logging
from src.database import DB_PATH
from src.result_verifier import verify_results
from src.backtester import run_backtesting_check
from src.historical_results import (
    fetch_nba_season_results,
    persist_outcomes as _persist_nba_outcomes_to_db,
)
from src.sports.config import current_nba_season

logger = setup_logging("WinStakeSettle")

ACTIVE_WINDOW_START = 10   # 10:00 inclusive
ACTIVE_WINDOW_END = 2      # 02:00 exclusive (ventana cruza medianoche)
TICK_INTERVAL_MINUTES = 60


def in_active_window(hour: int) -> bool:
    """True si la hora cae dentro de [10:00, 02:00) — ventana cruza medianoche."""
    return hour >= ACTIVE_WINDOW_START or hour < ACTIVE_WINDOW_END


def persist_nba_outcomes() -> int:
    """Fetcha resultados NBA de la temporada actual y los persiste en match_outcomes.

    Returns:
        Número de outcomes nuevos insertados (0 si todos ya existían o hay error).
    """
    try:
        season = current_nba_season()
        games = fetch_nba_season_results(season=season)
        stats = _persist_nba_outcomes_to_db(games, db_path=str(DB_PATH))
        return stats.get("inserted", 0)
    except Exception as e:
        logger.warning(f"Error persisting NBA outcomes: {e}")
        return 0


def settle_all() -> dict:
    """Ejecuta un ciclo de settle para LaLiga y NBA, aislando errores por deporte."""
    summary: dict = {"laliga": None, "nba": None, "nba_outcomes": None}

    if config.LALIGA_ENABLED:
        try:
            logger.info("⚽ Settle LaLiga (verify_pending)...")
            summary["laliga"] = verify_results()
        except Exception as e:
            logger.error(f"Error en settle LaLiga: {e}", exc_info=True)
            summary["laliga"] = {"error": str(e)}
    else:
        logger.info("LaLiga settle: skipped (disabled in config)")
        summary["laliga"] = {"skipped": True}

    try:
        logger.info("🏀 Settle NBA (run_backtesting_check)...")
        summary["nba"] = run_backtesting_check(str(DB_PATH))
    except Exception as e:
        logger.error(f"Error en settle NBA: {e}", exc_info=True)
        summary["nba"] = {"error": str(e)}

    n_outcomes = persist_nba_outcomes()
    if n_outcomes > 0:
        logger.info(f"Persistidos {n_outcomes} nuevos outcomes NBA")
    summary["nba_outcomes"] = n_outcomes

    logger.info(f"✅ Ciclo completado: {summary}")
    return summary


def tick() -> None:
    """Tick programado: settle si estamos en ventana activa, skip si no."""
    now = datetime.now()
    if not in_active_window(now.hour):
        logger.info(
            f"⏸️  {now.strftime('%H:%M')} fuera de ventana "
            f"[{ACTIVE_WINDOW_START:02d}:00–{ACTIVE_WINDOW_END:02d}:00). Skip."
        )
        return
    logger.info(f"⏱️  Tick {now.strftime('%H:%M')} — ejecutando settle")
    settle_all()


def main() -> None:
    logger.info("=" * 60)
    logger.info("🚀 WinStake.ia — Settle Daemon iniciado")
    logger.info(f"   Ventana activa: {ACTIVE_WINDOW_START:02d}:00–{ACTIVE_WINDOW_END:02d}:00")
    logger.info(f"   Cadencia: cada {TICK_INTERVAL_MINUTES} min")
    logger.info("=" * 60)

    tick()  # Tick inmediato al arrancar (si toca)
    schedule.every(TICK_INTERVAL_MINUTES).minutes.do(tick)

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Daemon detenido por usuario")
        sys.exit(0)


if __name__ == "__main__":
    main()
