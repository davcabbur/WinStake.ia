"""
WinStake.ia — Telegram Bot Daemon
Bot interactivo con botones inline para seleccionar partidos de la jornada.
"""

import logging
import asyncio
from dataclasses import replace as dataclass_replace
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
from src.nba_client import NBAClient
from src.analyzer import Analyzer
from src.formatter import Formatter
from src.nba_formatter import NBAFormatter
from src.sports.config import get_sport, SPORTS, SportConfig, LALIGA
from src.nba_props import generate_prop_recommendations
from src.ev_calculator import EVResult
from src.logger_config import setup_logging
from src.database import DB_PATH

logger = setup_logging("WinStakeBot")

# Umbral PPG para considerar a un jugador como "estrella"
_STAR_PPG_THRESHOLD = 18.0


def _apply_injury_impact(analysis, home_players: list, away_players: list, import_config) -> None:
    """
    Detecta jugadores estrella lesionados (Out/Doubtful) y:
    1. Añade injury_alerts al análisis para mostrarlos en la cajita de lesiones.
    2. Ajusta el EV del mejor pick automáticamente si el equipo recomendado tiene bajas.
       - Out confirmado (≥18 PPG): EV ×0.60
       - Doubtful/Questionable (≥18 PPG): EV ×0.80
    """
    player_map: dict[str, dict] = {}
    for p in home_players + away_players:
        player_map[p["player_name"].lower()] = p

    def _find_player(inj_name: str):
        low = inj_name.lower()
        for key, p in player_map.items():
            if low in key or key in low:
                return p
        return None

    alerts = []
    for side in ("home", "away"):
        team_name = analysis.home_team if side == "home" else analysis.away_team
        for inj in analysis.injuries.get(side, []):
            status_raw = inj.get("status", "")
            status_low = status_raw.lower()
            if not any(s in status_low for s in ("out", "doubtful", "questionable")):
                continue
            p = _find_player(inj["player"])
            ppg = p["pts_season"] if p else 0.0
            alerts.append({
                "player": inj["player"],
                "team": team_name,
                "status": status_raw,
                "detail": inj.get("detail", ""),
                "ppg": ppg,
                "is_star": ppg >= _STAR_PPG_THRESHOLD,
            })

    analysis.injury_alerts = sorted(alerts, key=lambda x: x["ppg"], reverse=True)

    # Ajuste de EV si la apuesta recomendada es sobre un equipo con baja estrella
    if not analysis.best_bet or not analysis.best_bet.is_value:
        return

    sel = analysis.best_bet.selection  # "Home", "Away", "Spread Home", "Spread Away"
    is_home_bet = sel in ("Home", "Spread Home")
    team_with_bet = analysis.home_team if is_home_bet else analysis.away_team
    side_with_bet = "home" if is_home_bet else "away"

    discount = 1.0
    for alert in analysis.injury_alerts:
        if alert["team"] != team_with_bet or not alert["is_star"]:
            continue
        status_low = alert["status"].lower()
        if "out" in status_low:
            discount = min(discount, 0.60)
        elif "doubtful" in status_low:
            discount = min(discount, 0.80)
        elif "questionable" in status_low:
            discount = min(discount, 0.90)

    if discount < 1.0:
        old_ev = analysis.best_bet.ev
        new_ev = old_ev * discount
        new_ev_pct = round(new_ev * 100, 2)
        # Improvement 9: use dataclasses.replace() instead of manual reconstruction
        analysis.best_bet = dataclass_replace(
            analysis.best_bet,
            ev=round(new_ev, 4),
            ev_percent=new_ev_pct,
            is_value=bool(new_ev >= import_config.MIN_EV_THRESHOLD),
        )
        if not analysis.best_bet.is_value:
            analysis.recommendation = "No apostar"
            analysis.confidence = "—"
        stars_out = [a["player"] for a in analysis.injury_alerts if a["team"] == team_with_bet and a["is_star"]]
        analysis.insights.insert(0,
            f"⚠️ EV ajustado x{discount:.0%} por lesiones en {team_with_bet}: "
            + ", ".join(stars_out)
        )


def _run_analysis_for_jornada(sport_config: SportConfig = None) -> dict:
    """
    Ejecuta el análisis completo de la jornada y devuelve un dict
    {match_id: MatchAnalysis} con todos los partidos.
    """
    sc = sport_config or LALIGA
    odds_client = OddsClient(sport_config=sc)
    
    if sc.sport_type == "basketball":
        stats_client = NBAClient()
    else:
        stats_client = FootballClient()
        
    analyzer = Analyzer(sport_config=sc)

    # 1. Obtener cuotas
    matches_odds = odds_client.get_upcoming_odds()
    if not matches_odds:
        raise RuntimeError("No se obtuvieron partidos. Verifica tu ODDS_API_KEY.")

    # 2. Obtener clasificación
    standings = stats_client.get_standings()

    # 3. Recalibrar modelo con datos reales
    analyzer.calibrate_from_standings(standings)

    # 4. Obtener goleadores (Si aplica)
    scorers = []
    if hasattr(stats_client, 'get_top_scorers'):
        scorers = stats_client.get_top_scorers()

    # 5. Analizar cada partido
    analyses = {}
    for match in matches_odds:
        home = match["home_team"]
        away = match["away_team"]
        odds = match["avg_odds"]
        match_id = match.get("id", f"{home}_{away}")

        home_stats = stats_client.find_team_in_standings(home, standings)
        away_stats = stats_client.find_team_in_standings(away, standings)

        h2h_data = []
        if home_stats and away_stats:
            home_id = home_stats.get("team_id")
            away_id = away_stats.get("team_id")
            if home_id and away_id:
                h2h_data = stats_client.get_h2h(home_id, away_id)

        # Goleadores del partido
        match_scorers = []
        if scorers and hasattr(stats_client, 'get_players_for_match'):
            match_scorers = stats_client.get_players_for_match(home, away, scorers)

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

    # 6. NBA — Player props, DvP, últimos 10, lesiones
    if sc.sport_type == "basketball":
        # Recoger team_ids de todos los partidos
        match_team_ids: dict[str, tuple] = {}
        for match in matches_odds:
            mid = match.get("id", f"{match['home_team']}_{match['away_team']}")
            hs = stats_client.find_team_in_standings(match["home_team"], standings)
            as_ = stats_client.find_team_in_standings(match["away_team"], standings)
            match_team_ids[mid] = (
                hs.get("team_id") if hs else None,
                as_.get("team_id") if as_ else None,
            )
        all_tids = list({tid for h, a in match_team_ids.values() for tid in (h, a) if tid})

        # Stats de jugadores (temporada + L10)
        player_stats = stats_client.get_player_stats_for_teams(all_tids)

        # Lesiones (1 sola llamada para todos los partidos)
        injuries_data = stats_client.get_injuries()

        for mid, (home_tid, away_tid) in match_team_ids.items():
            if mid not in analyses:
                continue
            a = analyses[mid]

            # Player props (stats)
            home_players = player_stats.get(home_tid, []) if home_tid else []
            away_players = player_stats.get(away_tid, []) if away_tid else []
            a.player_props = {"home": home_players, "away": away_players}

            # Últimos 10 partidos
            a.team_last10 = {
                "home": stats_client.get_team_last10(home_tid) if home_tid else [],
                "away": stats_client.get_team_last10(away_tid) if away_tid else [],
            }

            # DvP (Defense vs Position)
            home_dvp = stats_client.get_defense_vs_position(home_tid) if home_tid else {}
            away_dvp = stats_client.get_defense_vs_position(away_tid) if away_tid else {}

            # Posiciones de jugadores
            home_positions = stats_client.get_player_positions(home_tid) if home_tid else {}
            away_positions = stats_client.get_player_positions(away_tid) if away_tid else {}

            # Lesiones por equipo — usar abreviaciones ESPN correctas
            home_abbr = stats_client.get_espn_abbr(a.home_team)
            away_abbr = stats_client.get_espn_abbr(a.away_team)
            a.injuries = {
                "home": injuries_data.get(home_abbr, []),
                "away": injuries_data.get(away_abbr, []),
            }

            # ── Alertas de lesiones clave + ajuste automático de EV ──
            _apply_injury_impact(a, home_players, away_players, import_config=config)

            # Improvement 3: detect back-to-back teams for today's games
            game_date = datetime.now().strftime("%Y-%m-%d")
            b2b_teams = stats_client.get_back_to_back_teams(game_date)

            # Recomendaciones de props
            a.prop_recommendations = generate_prop_recommendations(
                home_team=a.home_team,
                away_team=a.away_team,
                home_players=home_players,
                away_players=away_players,
                home_dvp=home_dvp,
                away_dvp=away_dvp,
                home_positions=home_positions,
                away_positions=away_positions,
                home_team_id=home_tid,
                away_team_id=away_tid,
                b2b_teams=b2b_teams,
            )

    # 7. Guardar en BD + Improvement 8: line movement tracking
    db = Database()
    for match in matches_odds:
        mid = match.get("id", f"{match['home_team']}_{match['away_team']}")
        if mid not in analyses:
            continue
        a = analyses[mid]
        odds = match.get("avg_odds", {})
        p = a.probabilities

        spread_line = getattr(p, "market_spread", None) or None
        total_line = getattr(p, "market_total", None) or None
        home_odds = odds.get("home")
        away_odds = odds.get("away")

        # Save snapshot
        db.save_line_snapshot(
            match_id=mid,
            sport=sc.key,
            spread_line=spread_line,
            total_line=total_line,
            home_odds=home_odds,
            away_odds=away_odds,
        )

        # Detect movement vs previous snapshot
        movement_alert = db.detect_line_movement(
            match_id=mid,
            current_spread=spread_line,
            current_total=total_line,
            current_home_odds=home_odds,
            current_away_odds=away_odds,
        )
        if movement_alert:
            a.insights.append(movement_alert)

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

        # Construir teclado inline (devuelve también la lista ordenada)
        keyboard, sorted_matches = _build_match_keyboard(analyses, sport)

        # Guardar en caché para este chat
        _jornada_cache[chat_id] = {"analyses": analyses, "sport": sport, "sorted_matches": sorted_matches}
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

        # NBA: enviar Injury Report de ESPN como mensaje separado
        if sport.sport_type == "basketball":
            injury_report = NBAFormatter().format_injury_report(list(analyses.values()))
            if injury_report:
                for chunk in _split_message(injury_report):
                    await update.message.reply_html(chunk, disable_web_page_preview=True)

    except (SystemExit, RuntimeError) as e:
        logger.error(f"Error en análisis: {e}")
        await update.message.reply_text(f"⚠️ Error: {e}")
    except Exception as e:
        logger.error(f"Error forzando análisis: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error ejecutando el análisis. Revisa los logs.")


def _build_match_keyboard(analyses: dict, sport: SportConfig) -> tuple[list, list]:
    """Construye teclado inline con botones de partidos.

    Devuelve (keyboard, sorted_matches) donde sorted_matches es la lista
    ordenada usada para que los índices del callback coincidan.
    """
    keyboard = []
    sorted_analyses = sorted(analyses.values(), key=lambda a: a.commence_time or "")

    for i, a in enumerate(sorted_analyses):
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
        callback_data = f"match:{i}"  # índice numérico, siempre < 64 bytes

        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("📊 Ver Resumen Ejecutivo", callback_data="summary")])
    if sport.sport_type == "basketball":
        keyboard.append([InlineKeyboardButton("🎰 Combinada Recomendada", callback_data="parlay")])
    return keyboard, sorted_analyses


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
    formatter = NBAFormatter() if sport.sport_type == "basketball" else Formatter()

    if data == "summary":
        summary = formatter._format_summary(list(analyses.values()))
        chunks = _split_message(summary)
        for chunk in chunks:
            await query.message.reply_html(chunk, disable_web_page_preview=True)
        return

    if data.startswith("match:"):
        try:
            idx = int(data[6:])
        except ValueError:
            await query.message.reply_text("⚠️ Datos de partido inválidos.")
            return

        sorted_matches = cache.get("sorted_matches", [])
        if idx < 0 or idx >= len(sorted_matches):
            await query.message.reply_text("⚠️ Partido no encontrado en el análisis actual.")
            return

        analysis = sorted_matches[idx]
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

    if data == "parlay":
        from src.nba_formatter import NBAFormatter as _NBA
        from src.database import Database as _DB
        try:
            _roi = _DB().get_roi_summary(sport="nba")
        except Exception:
            _roi = None
        msg = _NBA().format_parlay(list(analyses.values()), roi_summary=_roi)
        chunks = _split_message(msg)
        back_button = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Volver a la jornada", callback_data="back_to_jornada")]
        ])
        for i, chunk in enumerate(chunks):
            markup = back_button if i == len(chunks) - 1 else None
            try:
                await query.message.reply_html(chunk, disable_web_page_preview=True, reply_markup=markup)
            except Exception:
                await query.message.reply_text(_strip_html(chunk), reply_markup=markup)
        return

    if data == "back_to_jornada":
        keyboard, _ = _build_match_keyboard(analyses, sport)

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


async def _daily_backtesting_task():
    """
    Improvement 7: Daily background task that runs backtesting at 10:00 AM.
    Checks unresolved picks and updates WIN/LOSS/PUSH results.
    """
    while True:
        try:
            now = datetime.now()
            # Calculate seconds until next 10:00 AM
            target = now.replace(hour=10, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target.replace(day=target.day + 1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"Backtesting diario programado en {wait_seconds/3600:.1f}h")
            await asyncio.sleep(wait_seconds)

            # Run backtesting
            try:
                from src.backtester import run_backtesting_check
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: run_backtesting_check(DB_PATH))
                logger.info("Backtesting diario completado")
            except Exception as e:
                logger.error(f"Error en backtesting diario: {e}", exc_info=True)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error en tarea de backtesting: {e}", exc_info=True)
            await asyncio.sleep(3600)  # retry in 1h on unexpected error


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

    # Improvement 7: start daily backtesting background task
    async def post_init(app):
        asyncio.create_task(_daily_backtesting_task())

    application.post_init = post_init
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
