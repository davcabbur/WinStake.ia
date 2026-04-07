"""
WinStake.ia — Telegram Bot Daemon
Bot interactivo con botones inline para seleccionar partidos de la jornada.
"""

import logging
import asyncio
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.database import Database
from src.odds_client import OddsClient
from src.football_client import FootballClient
from src.analyzer import Analyzer
from src.formatter import Formatter
from src.sports.config import get_sport, SPORTS, SportConfig, LALIGA
from src.logger_config import setup_logging

logger = setup_logging("WinStakeBot")


def _run_analysis_for_jornada(sport_config: SportConfig = None) -> dict:
    """
    Ejecuta el análisis completo de la jornada y devuelve un dict
    {match_id: MatchAnalysis} con todos los partidos.
    """
    sc = sport_config or LALIGA
    odds_client = OddsClient(sport_config=sc)
    football_client = FootballClient()
    analyzer = Analyzer(sport_config=sc)

    # 1. Obtener cuotas
    matches_odds = odds_client.get_upcoming_odds()
    if not matches_odds:
        raise RuntimeError("No se obtuvieron partidos. Verifica tu ODDS_API_KEY.")

    # 2. Obtener clasificación
    standings = football_client.get_standings()

    # 3. Recalibrar modelo con datos reales
    analyzer.calibrate_from_standings(standings)

    # 4. Obtener goleadores
    scorers = football_client.get_top_scorers()

    # 5. Analizar cada partido
    analyses = {}
    for match in matches_odds:
        home = match["home_team"]
        away = match["away_team"]
        odds = match["avg_odds"]
        match_id = match.get("id", f"{home}_{away}")

        home_stats = football_client.find_team_in_standings(home, standings)
        away_stats = football_client.find_team_in_standings(away, standings)

        h2h_data = []
        if home_stats and away_stats:
            home_id = home_stats.get("team_id")
            away_id = away_stats.get("team_id")
            if home_id and away_id:
                h2h_data = football_client.get_h2h(home_id, away_id)

        # Goleadores del partido
        match_scorers = football_client.get_players_for_match(home, away, scorers)

        analysis = analyzer.analyze_match(
            home_team=home,
            away_team=away,
            odds=odds,
            home_stats=home_stats,
            away_stats=away_stats,
            commence_time=match.get("commence_time", ""),
            h2h_data=h2h_data,
            match_id=match_id,
            scorers=match_scorers,
        )
        analyses[match_id] = analysis

    # 6. Guardar en BD
    db = Database()
    for analysis in analyses.values():
        db.save_analysis(analysis, sport=sc.key)

    return analyses


# ── Almacenamiento en memoria por chat ──────────────────────
# {chat_id: {"analyses": {...}, "sport": SportConfig}}
_jornada_cache: dict[int, dict] = {}


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador para /start o /help."""
    msg = (
        "🤖 <b>WinStake.ia — Bot de Análisis Multi-Deporte</b>\n\n"
        "Comandos disponibles:\n"
        "⚽ /laliga — Analizar la próxima jornada de La Liga\n"
        "🏀 /nba — Analizar los próximos partidos NBA\n"
        "🔹 /analizar — Analizar La Liga (default)\n"
        "🔹 /roi — Consultar tu Bankroll y ROI histórico\n"
        "🔹 /ping — Verificar estado del motor\n\n"
        "Pulsa un comando de deporte para empezar."
    )
    await update.message.reply_html(msg)


async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador para /ping."""
    await update.message.reply_text("✅ Motor WinStake.ia operativo y esperando órdenes.")


async def roi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Consulta en SQLite el ROI actual y lo devuelve."""
    db = Database()
    roi = db.get_roi_summary()

    if roi["total_bets"] == 0:
        await update.message.reply_text("📉 Todavía no hay apuestas registradas en la base de datos.")
        return

    msg = (
        f"📊 <b>Resumen de Rendimiento</b>\n\n"
        f"💰 <b>Total Apuestas:</b> {roi['total_bets']}\n"
        f"✅ <b>Ganadas:</b> {roi['wins']}\n"
        f"❌ <b>Perdidas:</b> {roi['losses']}\n"
        f"💵 <b>Profit Neto:</b> {roi['total_profit']:+.2f} unidades\n"
        f"📈 <b>ROI:</b> {roi['roi_percent']:+.2f}%\n"
    )
    await update.message.reply_html(msg)


async def _analizar_sport(update: Update, context: ContextTypes.DEFAULT_TYPE, sport_key: str = "laliga"):
    """
    Analiza la jornada completa de un deporte y muestra botones inline.
    """
    sport = get_sport(sport_key)
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"⏳ Analizando {sport.emoji} {sport.name}... Esto puede tardar unos segundos.")

    try:
        loop = asyncio.get_running_loop()
        analyses = await loop.run_in_executor(
            None, lambda: _run_analysis_for_jornada(sport)
        )

        if not analyses:
            await update.message.reply_text("❌ No se encontraron partidos para analizar.")
            return

        # Guardar en caché para este chat
        _jornada_cache[chat_id] = {"analyses": analyses, "sport": sport}

        # Construir teclado inline
        keyboard = _build_match_keyboard(analyses, sport)
        reply_markup = InlineKeyboardMarkup(keyboard)

        n_total = len(analyses)
        n_value = sum(1 for a in analyses.values() if a.best_bet and a.best_bet.is_value)

        header = (
            f"🏆 <b>WINSTAKE.IA — {sport.name.upper()}</b>\n"
            f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            f"{sport.emoji} {n_total} partidos analizados\n"
            f"🎯 {n_value} con valor detectado\n\n"
            f"Pulsa un partido para ver su análisis completo:"
        )

        await update.message.reply_html(header, reply_markup=reply_markup)

    except (SystemExit, RuntimeError) as e:
        logger.error(f"Error en análisis: {e}")
        await update.message.reply_text(f"⚠️ Error: {e}")
    except Exception as e:
        logger.error(f"Error forzando análisis: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error ejecutando el análisis. Revisa los logs.")


def _build_match_keyboard(analyses: dict, sport: SportConfig) -> list:
    """Construye teclado inline con botones de partidos."""
    keyboard = []
    sorted_analyses = sorted(analyses.values(), key=lambda a: a.commence_time or "")

    for a in sorted_analyses:
        if a.best_bet and a.best_bet.is_value:
            icon = "✅"
            ev_text = f" | EV: {a.best_bet.ev_percent:+.1f}%"
        else:
            icon = sport.emoji
            ev_text = ""

        date_str = ""
        if a.commence_time:
            try:
                dt = datetime.fromisoformat(a.commence_time.replace("Z", "+00:00"))
                date_str = f" ({dt.strftime('%d/%m %H:%M')})"
            except (ValueError, AttributeError):
                pass

        button_text = f"{icon} {a.home_team} vs {a.away_team}{date_str}{ev_text}"
        callback_data = f"match:{a.match_id}"

        if len(callback_data.encode('utf-8')) > 64:
            callback_data = f"match:{a.match_id[:50]}"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("📊 Ver Resumen Ejecutivo", callback_data="summary")])
    return keyboard


async def analizar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Atajo para /analizar (default: La Liga)."""
    await _analizar_sport(update, context, "laliga")


async def laliga_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analizar La Liga."""
    await _analizar_sport(update, context, "laliga")


async def nba_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Analizar NBA."""
    await _analizar_sport(update, context, "nba")


async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja los clics en los botones inline."""
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data

    if chat_id not in _jornada_cache:
        await query.message.reply_text(
            "⚠️ No hay análisis en memoria. Ejecuta /analizar, /laliga o /nba primero.",
        )
        return

    cache = _jornada_cache[chat_id]
    analyses = cache["analyses"]
    sport = cache["sport"]
    formatter = Formatter()

    if data == "summary":
        summary = formatter._format_summary(list(analyses.values()))
        chunks = _split_message(summary)
        for chunk in chunks:
            await query.message.reply_html(chunk, disable_web_page_preview=True)
        return

    if data.startswith("match:"):
        match_id = data[6:]

        if match_id not in analyses:
            await query.message.reply_text("⚠️ Partido no encontrado en el análisis actual.")
            return

        analysis = analyses[match_id]
        msg = formatter.format_single_match(analysis)

        back_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Volver a la jornada", callback_data="back_to_jornada")]
        ])

        chunks = _split_message(msg)
        for i, chunk in enumerate(chunks):
            reply_markup = back_button if i == len(chunks) - 1 else None
            try:
                await query.message.reply_html(
                    chunk, disable_web_page_preview=True, reply_markup=reply_markup,
                )
            except Exception:
                await query.message.reply_text(
                    _strip_html(chunk), disable_web_page_preview=True, reply_markup=reply_markup,
                )
        return

    if data == "back_to_jornada":
        keyboard = _build_match_keyboard(analyses, sport)

        n_total = len(analyses)
        n_value = sum(1 for a in analyses.values() if a.best_bet and a.best_bet.is_value)

        header = (
            f"🏆 <b>WINSTAKE.IA — {sport.name.upper()}</b>\n"
            f"{sport.emoji} {n_total} partidos | 🎯 {n_value} con valor\n\n"
            f"Pulsa un partido para ver su análisis:"
        )

        await query.message.reply_html(
            header, reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return


def _split_message(text: str, max_length: int = 4096) -> list[str]:
    """Divide un mensaje largo en chunks."""
    if len(text) <= max_length:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_pos = text.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        chunks.append(text[:split_pos])
        text = text[split_pos:].lstrip("\n")
    return chunks


def _strip_html(text: str) -> str:
    """Elimina tags HTML."""
    import re
    return re.sub(r"<[^>]+>", "", text)


def main():
    """Inicia el demonio del bot."""
    token = config.TELEGRAM_BOT_TOKEN

    if not token or token == "tu_token_aqui":
        logger.error("🛑 TELEGRAM_BOT_TOKEN no configurado en '.env'. Abortando demonio del bot.")
        return

    application = Application.builder().token(token).build()

    # Comandos
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("roi", roi_command))
    application.add_handler(CommandHandler("analizar", analizar_command))
    application.add_handler(CommandHandler("laliga", laliga_command))
    application.add_handler(CommandHandler("nba", nba_command))

    # Callbacks de botones inline
    application.add_handler(CallbackQueryHandler(match_callback))

    logger.info("🚀 WinStake.ia Bot Daemon iniciado. Escuchando comandos de Telegram...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
