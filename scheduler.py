"""
WinStake.ia — Scheduler Multi-Deporte
Ejecuta el análisis de forma programada para La Liga y/o NBA.

Modos de uso:
    1. Scheduler continuo (deja corriendo):
       python scheduler.py                  # Ambos deportes
       python scheduler.py --sport laliga   # Solo La Liga
       python scheduler.py --sport nba      # Solo NBA

    2. Ejecución única (para Windows Task Scheduler):
       python scheduler.py --once
       python scheduler.py --once --sport nba
"""

import sys
import time
import logging
import argparse
from datetime import datetime

import schedule

from main import main as run_analysis
from src.sports.config import SPORTS

from src.logger_config import setup_logging

logger = setup_logging("Scheduler")

# ── Configuración de horarios por deporte ────────────────────

SPORT_SCHEDULES = {
    "laliga": {
        "name": "La Liga",
        "times": [
            ("friday", "10:00"),
            ("saturday", "09:00"),
            ("sunday", "09:00"),
            ("tuesday", "10:00"),
            ("wednesday", "10:00"),
        ],
    },
    "nba": {
        "name": "NBA",
        "times": [
            ("monday", "16:00"),
            ("tuesday", "16:00"),
            ("wednesday", "16:00"),
            ("thursday", "16:00"),
            ("friday", "16:00"),
            ("saturday", "14:00"),
            ("sunday", "14:00"),
        ],
    },
}


def safe_run(sport: str = "laliga"):
    """Ejecuta el análisis con manejo de errores."""
    try:
        sport_name = SPORT_SCHEDULES.get(sport, {}).get("name", sport)
        logger.info("=" * 50)
        logger.info(f"Ejecucion programada: {sport_name}")
        logger.info(f"{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        logger.info("=" * 50)
        run_analysis(["--sport", sport])
        logger.info(f"Ejecucion {sport_name} completada\n")
    except Exception as e:
        logger.error(f"Error en ejecucion programada ({sport}): {e}\n", exc_info=True)


def setup_schedule(sports: list[str]):
    """Configura los horarios de ejecucion para los deportes indicados."""
    for sport in sports:
        conf = SPORT_SCHEDULES.get(sport)
        if not conf:
            logger.warning(f"Deporte '{sport}' no tiene schedule configurado")
            continue

        logger.info(f"\n{conf['name']}:")
        for day, time_str in conf["times"]:
            day_scheduler = getattr(schedule.every(), day)
            day_scheduler.at(time_str).do(safe_run, sport=sport)
            logger.info(f"  {day.capitalize()} a las {time_str}")


def run_continuous(sports: list[str]):
    """Modo daemon: corre continuamente ejecutando segun horario."""
    logger.info("WinStake.ia Scheduler iniciado")
    logger.info(f"Deportes: {', '.join(sports)}")
    logger.info("Horarios configurados:")

    setup_schedule(sports)

    logger.info(f"\n{len(schedule.get_jobs())} tareas programadas")
    next_run = schedule.next_run()
    logger.info(f"Proxima ejecucion: {next_run.strftime('%A %d/%m/%Y %H:%M') if next_run else 'N/A'}")
    logger.info("\nEsperando... (Ctrl+C para detener)\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("\nScheduler detenido por el usuario")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="WinStake.ia Scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecutar el analisis una sola vez y salir",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Ejecutar inmediatamente una vez, luego continuar con el scheduler",
    )
    parser.add_argument(
        "--sport",
        type=str,
        default=None,
        help="Deporte a analizar: laliga, nba, o 'all' para ambos (default: all)",
    )
    args = parser.parse_args()

    if args.sport and args.sport != "all":
        if args.sport not in SPORTS:
            available = ", ".join(SPORTS.keys())
            logger.error(f"Deporte '{args.sport}' no valido. Disponibles: {available}")
            sys.exit(1)
        sports = [args.sport]
    else:
        sports = list(SPORT_SCHEDULES.keys())

    if args.once:
        logger.info("Modo ejecucion unica (--once)")
        for sport in sports:
            safe_run(sport)
    elif args.test:
        logger.info("Modo test: ejecutando analisis ahora...")
        for sport in sports:
            safe_run(sport)
        logger.info("Test completado. Iniciando scheduler continuo...\n")
        run_continuous(sports)
    else:
        run_continuous(sports)


if __name__ == "__main__":
    main()
