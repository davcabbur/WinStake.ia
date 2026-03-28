"""
WinStake.ia — Entry Point
Orquesta: obtener datos → analizar → formatear → enviar a Telegram.
"""

import sys
import logging
from datetime import datetime

import config
from src.odds_client import OddsClient
from src.football_client import FootballClient
from src.analyzer import Analyzer
from src.formatter import Formatter
from src.telegram_bot import TelegramSender
from src.database import Database

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("WinStake")


def main():
    """Flujo principal de WinStake.ia."""
    start_time = datetime.now()
    logger.info("🚀 WinStake.ia iniciando análisis...")

    # ── 1. Inicializar clientes ──────────────────────────
    odds_client = OddsClient()
    football_client = FootballClient()
    analyzer = Analyzer()
    formatter = Formatter()
    telegram = TelegramSender()
    db = Database()

    # ── 2. Obtener cuotas ────────────────────────────────
    logger.info("📊 Obteniendo cuotas de mercado...")
    matches_odds = odds_client.get_upcoming_odds()

    if not matches_odds:
        logger.error("❌ No se obtuvieron partidos. Verifica tu ODDS_API_KEY.")
        sys.exit(1)

    logger.info(f"   → {len(matches_odds)} partidos con cuotas")

    # ── 3. Obtener clasificación ─────────────────────────
    logger.info("📈 Obteniendo clasificación y estadísticas...")
    standings = football_client.get_standings()
    logger.info(f"   → {len(standings)} equipos en clasificación")

    # ── 4. Analizar cada partido ─────────────────────────
    logger.info("🧠 Ejecutando análisis cuantitativo...\n")
    analyses = []

    for match in matches_odds:
        home = match["home_team"]
        away = match["away_team"]
        odds = match["avg_odds"]

        logger.info(f"   Analizando: {home} vs {away}")

        # Buscar stats en standings
        home_stats = football_client.find_team_in_standings(home, standings)
        away_stats = football_client.find_team_in_standings(away, standings)

        # Obtener H2H (historial directo)
        h2h_data = []
        if home_stats and away_stats:
            home_id = home_stats.get("team_id")
            away_id = away_stats.get("team_id")
            if home_id and away_id:
                h2h_data = football_client.get_h2h(home_id, away_id)
                if h2h_data:
                    logger.info(f"      📜 H2H: {len(h2h_data)} enfrentamientos previos")

        # Ejecutar análisis
        analysis = analyzer.analyze_match(
            home_team=home,
            away_team=away,
            odds=odds,
            home_stats=home_stats,
            away_stats=away_stats,
            commence_time=match.get("commence_time", ""),
            h2h_data=h2h_data,
        )
        analyses.append(analysis)

        # Log resultado
        if analysis.best_bet and analysis.best_bet.is_value:
            logger.info(
                f"   ✅ VALUE BET: {analysis.best_bet.selection} "
                f"@ {analysis.best_bet.odds:.2f} (EV: {analysis.best_bet.ev_percent:+.1f}%)"
            )
        else:
            logger.info("   ❌ Sin valor")

    # ── 5. Persistencia ──────────────────────────────────
    logger.info("\n💾 Guardando análisis en base de datos...")
    saved_count = 0
    value_saved = 0
    for analysis in analyses:
        db.save_analysis(analysis)
        saved_count += 1
        if analysis.best_bet and analysis.best_bet.is_value:
            value_saved += 1
    logger.info(f"   → {saved_count} análisis guardados, {value_saved} value bets registradas")

    # ── 6. Resumen ───────────────────────────────────────
    value_count = sum(1 for a in analyses if a.best_bet and a.best_bet.is_value)
    logger.info(f"\n📊 Resumen: {value_count}/{len(analyses)} partidos con valor")

    # ROI acumulado
    roi = db.get_roi_summary()
    if roi["total_bets"] > 0:
        logger.info(
            f"📈 ROI acumulado: {roi['roi_percent']:+.1f}% "
            f"({roi['wins']}W-{roi['losses']}L, {roi['total_profit']:+.1f}u)"
        )

    # ── 7. Formatear ─────────────────────────────────────
    logger.info("📝 Formateando reporte...")
    messages = formatter.format_full_report(analyses)
    logger.info(f"   → {len(messages)} mensajes generados")

    # ── 8. Enviar a Telegram ─────────────────────────────
    logger.info("📲 Enviando a Telegram...")
    success = telegram.send_messages(messages)

    # ── 9. Resultado ─────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    if success:
        logger.info(f"\n✅ Análisis completado en {elapsed:.1f}s")
    else:
        logger.error(f"\n❌ Error en el envío. Tiempo: {elapsed:.1f}s")
        sys.exit(1)


if __name__ == "__main__":
    main()
