"""
WinStake.ia — Scheduler
Ejecuta el análisis de forma programada.

Modos de uso:
    1. Scheduler continuo (deja corriendo):
       python scheduler.py

    2. Ejecución única (para Windows Task Scheduler):
       python scheduler.py --once
"""

import sys
import time
import logging
import argparse
from datetime import datetime

import schedule

from main import main as run_analysis

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("winstake_scheduler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("Scheduler")

# ── Configuración de horarios ─────────────────────────────
# La Liga: partidos viernes, sábado y domingo
# Análisis se ejecuta antes de la jornada

SCHEDULE_TIMES = {
    "friday":    "10:00",   # Viernes 10:00 — antes del partido nocturno
    "saturday":  "09:00",   # Sábado 09:00 — antes de los partidos del día
    "sunday":    "09:00",   # Domingo 09:00 — antes de los partidos del día
    "midweek":   "10:00",   # Martes/miércoles — para jornadas entre semana
}


def safe_run():
    """Ejecuta el análisis con manejo de errores."""
    try:
        logger.info("=" * 50)
        logger.info("⏰ Ejecución programada iniciada")
        logger.info(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        logger.info("=" * 50)
        run_analysis()
        logger.info("✅ Ejecución programada completada correctamente\n")
    except Exception as e:
        logger.error(f"❌ Error en ejecución programada: {e}\n", exc_info=True)


def setup_schedule():
    """Configura los horarios de ejecución."""

    # Viernes
    schedule.every().friday.at(SCHEDULE_TIMES["friday"]).do(safe_run)
    logger.info(f"📅 Viernes a las {SCHEDULE_TIMES['friday']}")

    # Sábado
    schedule.every().saturday.at(SCHEDULE_TIMES["saturday"]).do(safe_run)
    logger.info(f"📅 Sábado a las {SCHEDULE_TIMES['saturday']}")

    # Domingo
    schedule.every().sunday.at(SCHEDULE_TIMES["sunday"]).do(safe_run)
    logger.info(f"📅 Domingo a las {SCHEDULE_TIMES['sunday']}")

    # Martes (jornadas entre semana)
    schedule.every().tuesday.at(SCHEDULE_TIMES["midweek"]).do(safe_run)
    logger.info(f"📅 Martes a las {SCHEDULE_TIMES['midweek']}")

    # Miércoles (jornadas entre semana)
    schedule.every().wednesday.at(SCHEDULE_TIMES["midweek"]).do(safe_run)
    logger.info(f"📅 Miércoles a las {SCHEDULE_TIMES['midweek']}")


def run_continuous():
    """Modo daemon: corre continuamente ejecutando según horario."""
    logger.info("🚀 WinStake.ia Scheduler iniciado")
    logger.info("Horarios configurados:\n")

    setup_schedule()

    logger.info(f"\n📊 {len(schedule.get_jobs())} tareas programadas")
    next_run = schedule.next_run()
    logger.info(f"⏭️  Próxima ejecución: {next_run.strftime('%A %d/%m/%Y %H:%M') if next_run else 'N/A'}")
    logger.info("\n💤 Esperando... (Ctrl+C para detener)\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)  # Comprobar cada 30 segundos
    except KeyboardInterrupt:
        logger.info("\n🛑 Scheduler detenido por el usuario")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="WinStake.ia Scheduler")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecutar el análisis una sola vez y salir (para Task Scheduler)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Ejecutar inmediatamente una vez para probar, luego continuar con el scheduler",
    )
    args = parser.parse_args()

    if args.once:
        logger.info("🔄 Modo ejecución única (--once)")
        safe_run()
    elif args.test:
        logger.info("🧪 Modo test: ejecutando análisis ahora...")
        safe_run()
        logger.info("✅ Test completado. Iniciando scheduler continuo...\n")
        run_continuous()
    else:
        run_continuous()


if __name__ == "__main__":
    main()
