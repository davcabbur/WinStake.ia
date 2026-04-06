"""
WinStake.ia — Entry Point
Orquesta: obtener datos → analizar → formatear → enviar a Telegram.
"""

import sys
import csv
import logging
import argparse
from datetime import datetime

import config
from src.odds_client import OddsClient
from src.football_client import FootballClient
from src.analyzer import Analyzer
from src.formatter import Formatter
from src.telegram_bot import TelegramSender
from src.database import Database

from src.logger_config import setup_logging

# ── Logging ───────────────────────────────────────────────
logger = setup_logging("WinStake")


def parse_args(args=None):
    """Parsea argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="WinStake.ia — Análisis cuantitativo de apuestas La Liga",
    )
    parser.add_argument(
        "--mock-mode",
        action="store_true",
        help="Usar datos simulados sin llamar a las APIs reales",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ejecutar análisis sin enviar mensajes a Telegram ni guardar en BD",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        metavar="FILE",
        help="Exportar resultados a un archivo CSV",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Activar logging en modo DEBUG",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verificar resultados de value bets pendientes y salir",
    )
    parser.add_argument(
        "--backtest",
        type=int,
        metavar="SEASON",
        help="Ejecutar backtest en una temporada (ej: 23 para 2023/24)",
    )
    return parser.parse_args(args)


def export_csv(analyses: list, filepath: str):
    """Exporta los análisis a CSV."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "home_team", "away_team", "commence_time",
            "prob_home", "prob_draw", "prob_away",
            "prob_over25", "lambda_home", "lambda_away",
            "odds_home", "odds_draw", "odds_away", "odds_over25", "odds_under25",
            "best_selection", "best_odds", "ev_percent",
            "kelly_half", "stake_units", "confidence",
        ])
        for a in analyses:
            p = a.probabilities
            odds = a.market_odds
            writer.writerow([
                a.home_team, a.away_team, a.commence_time,
                f"{p.home_win:.4f}", f"{p.draw:.4f}", f"{p.away_win:.4f}",
                f"{p.over_25:.4f}", f"{p.lambda_home:.3f}", f"{p.lambda_away:.3f}",
                odds.get("home", ""), odds.get("draw", ""), odds.get("away", ""),
                odds.get("over_25", ""), odds.get("under_25", ""),
                a.best_bet.selection if a.best_bet else "",
                f"{a.best_bet.odds:.2f}" if a.best_bet else "",
                f"{a.best_bet.ev_percent:.2f}" if a.best_bet else "",
                f"{a.kelly.kelly_half:.2f}" if a.kelly else "",
                f"{a.kelly.stake_units:.1f}" if a.kelly else "",
                a.confidence,
            ])
    logger.info(f"📄 Resultados exportados a {filepath}")


def main(cli_args: list = None):
    """
    Flujo principal de WinStake.ia.

    Args:
        cli_args: Lista de argumentos CLI. Si es None, usa sys.argv.
                  Pasar [] desde bot_daemon para usar defaults.
    """
    args = parse_args() if cli_args is None else parse_args(cli_args)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Modo verificación
    if args.verify:
        from src.result_verifier import verify_results
        logger.info("🔍 Verificando resultados pendientes...")
        verify_results()
        return

    # Modo backtest
    if args.backtest is not None:
        from src.backtester.engine import run_backtest
        from src.calibration import print_calibration_report
        logger.info(f"📊 Ejecutando backtest temporada {args.backtest}...")
        result = run_backtest(season=args.backtest)
        logger.info(f"\n{'='*50}")
        logger.info(f"ROI: {result.roi_percent:+.2f}%")
        logger.info(f"Bets: {result.total_bets} ({result.wins}W-{result.losses}L)")
        logger.info(f"Win Rate: {result.win_rate:.1f}%")
        logger.info(f"Bankroll: {result.initial_bankroll} → {result.final_bankroll:.1f}")
        logger.info(f"Max Drawdown: {result.max_drawdown:.1f}%")
        logger.info(f"Racha perdedora más larga: {result.longest_losing_streak}")
        logger.info(f"Odds promedio: {result.avg_odds:.2f}")
        logger.info(f"EV promedio: {result.avg_ev:.1f}%")
        if result.profit_by_market:
            logger.info(f"\nProfit por mercado:")
            for mkt, profit in sorted(result.profit_by_market.items(), key=lambda x: x[1], reverse=True):
                info = result.bets_by_market[mkt]
                logger.info(f"  {mkt}: {profit:+.1f}u ({info['wins']}/{info['total']} wins)")
        if result.predictions:
            logger.info(f"\n{'='*50}")
            print_calibration_report(result.predictions)
        return

    start_time = datetime.now()
    logger.info("🚀 WinStake.ia iniciando análisis...")

    if args.dry_run:
        logger.info("   ⚠️  Modo dry-run: sin Telegram ni BD")
    if args.mock_mode:
        logger.info("   🔧 Modo mock: datos simulados")

    # ── 1. Inicializar clientes ──────────────────────────
    odds_client = OddsClient()
    football_client = FootballClient()
    analyzer = Analyzer()
    formatter = Formatter()

    if args.mock_mode:
        odds_client._mock_mode = True
        football_client._mock_mode = True

    # ── 2. Obtener cuotas ────────────────────────────────
    logger.info("📊 Obteniendo cuotas de mercado...")
    matches_odds = odds_client.get_upcoming_odds()

    if not matches_odds:
        logger.error("❌ No se obtuvieron partidos. Verifica tu ODDS_API_KEY.")
        raise RuntimeError("No se obtuvieron partidos. Verifica tu ODDS_API_KEY.")

    logger.info(f"   → {len(matches_odds)} partidos con cuotas")

    # ── 3. Obtener clasificación ─────────────────────────
    logger.info("📈 Obteniendo clasificación y estadísticas...")
    standings = football_client.get_standings()
    logger.info(f"   → {len(standings)} equipos en clasificación")

    # Recalibrar media de goles desde datos reales
    analyzer.calibrate_from_standings(standings)

    # ── 4. Obtener goleadores ───────────────────────────
    logger.info("⚽ Obteniendo goleadores de La Liga...")
    scorers = football_client.get_top_scorers()
    logger.info(f"   → {len(scorers)} goleadores cargados")

    # ── 5. Analizar cada partido ─────────────────────────
    logger.info("🧠 Ejecutando análisis cuantitativo...\n")
    analyses = []

    for match in matches_odds:
        home = match["home_team"]
        away = match["away_team"]
        odds = match["avg_odds"]

        logger.info(f"   Analizando: {home} vs {away}")

        home_stats = football_client.find_team_in_standings(home, standings)
        away_stats = football_client.find_team_in_standings(away, standings)

        h2h_data = []
        if home_stats and away_stats:
            home_id = home_stats.get("team_id")
            away_id = away_stats.get("team_id")
            if home_id and away_id:
                h2h_data = football_client.get_h2h(home_id, away_id)
                if h2h_data:
                    logger.info(f"      📜 H2H: {len(h2h_data)} enfrentamientos previos")

        match_scorers = football_client.get_players_for_match(home, away, scorers)

        analysis = analyzer.analyze_match(
            home_team=home,
            away_team=away,
            odds=odds,
            home_stats=home_stats,
            away_stats=away_stats,
            commence_time=match.get("commence_time", ""),
            h2h_data=h2h_data,
            match_id=match.get("id", f"{home}_{away}"),
            scorers=match_scorers,
        )
        analyses.append(analysis)

        if analysis.best_bet and analysis.best_bet.is_value:
            logger.info(
                f"   ✅ VALUE BET: {analysis.best_bet.selection} "
                f"@ {analysis.best_bet.odds:.2f} (EV: {analysis.best_bet.ev_percent:+.1f}%)"
            )
        else:
            logger.info("   ❌ Sin valor")

    # ── 6. Persistencia ──────────────────────────────────
    if not args.dry_run:
        db = Database()
        logger.info("\n💾 Guardando análisis en base de datos...")
        saved_count = 0
        value_saved = 0
        for analysis in analyses:
            db.save_analysis(analysis)
            saved_count += 1
            if analysis.best_bet and analysis.best_bet.is_value:
                value_saved += 1
        logger.info(f"   → {saved_count} análisis guardados, {value_saved} value bets registradas")

        roi = db.get_roi_summary()
        if roi["total_bets"] > 0:
            logger.info(
                f"📈 ROI acumulado: {roi['roi_percent']:+.1f}% "
                f"({roi['wins']}W-{roi['losses']}L, {roi['total_profit']:+.1f}u)"
            )

    # ── 7. Export CSV ────────────────────────────────────
    if args.output_csv:
        export_csv(analyses, args.output_csv)

    # ── 8. Resumen ───────────────────────────────────────
    value_count = sum(1 for a in analyses if a.best_bet and a.best_bet.is_value)
    logger.info(f"\n📊 Resumen: {value_count}/{len(analyses)} partidos con valor")

    # ── 9. Formatear y Enviar ────────────────────────────
    if value_count > 0 and not args.dry_run:
        logger.info("📝 Formateando reporte (solo partidos con Value)...")
        value_analyses = [a for a in analyses if a.best_bet and a.best_bet.is_value]
        messages = formatter.format_full_report(value_analyses)
        logger.info(f"   → {len(messages)} mensajes generados")

        telegram = TelegramSender()
        logger.info("📲 Enviando a Telegram...")
        success = telegram.send_messages(messages)
    elif value_count > 0 and args.dry_run:
        logger.info("📝 Dry-run: reporte generado pero no enviado")
        success = True
    else:
        logger.info("🛑 No se detectaron Value Bets. No se envía mensaje a Telegram.")
        success = True

    # ── 10. Resultado ────────────────────────────────────
    elapsed = (datetime.now() - start_time).total_seconds()
    if success:
        logger.info(f"\n✅ Análisis completado en {elapsed:.1f}s")
    else:
        logger.error(f"\n❌ Error en el envío. Tiempo: {elapsed:.1f}s")
        raise RuntimeError("Error en el envío a Telegram")


if __name__ == "__main__":
    main()
