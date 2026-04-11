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
from src.blowout_adjuster import detect_blowout, adjust_over_for_blowout
from src.normal_model import NormalModel as _NormalModel
from src.ev_calculator import EVResult
from src.logger_config import setup_logging
from src.database import DB_PATH
from src.lineup_monitor import LineupMonitor, format_lineup_update

logger = setup_logging("WinStakeBot")

# Umbral PPG para considerar a un jugador como "estrella"
_STAR_PPG_THRESHOLD = 18.0

# TIER_1: superestrellas cuya baja impacta la eficiencia ofensiva del equipo más
# allá de sus PPG (system players, usage muy alto, generadores de juego únicos).
# Matching por fragmento de nombre en minúsculas.
_TIER_1_FRAGMENTS = frozenset({
    "curry", "embiid", "jokic", "giannis", "antetokounmpo",
    "doncic", "durant", "james", "tatum", "leonard",
    "lillard", "booker", "butler", "davis", "mitchell",
    "edwards", "wembanyama", "gilgeous-alexander", "sga",
})
# Reducción porcentual sobre el total proyectado cuando TIER_1 está Out
_TIER1_TOTAL_REDUCTION = 0.04   # 4%


def _apply_injury_impact(analysis, home_players: list, away_players: list, import_config) -> None:
    """
    Detecta jugadores estrella lesionados y aplica dos capas de ajuste:

    CAPA 1 — Alertas:
      Construye injury_alerts con PPG real del jugador para mostrar en el reporte.

    CAPA 2 — Ajuste de scores proyectados (total):
      Reduce home_score / away_score proporcionalmente al PPG perdido por lesiones.
      Replacement rate 30%: otros jugadores absorben ~30% del PPG perdido.
      Floor: nunca reducir más del 25% del score base.
      Recalcula over_total / under_total con distribución Normal ajustada.

    CAPA 3 — Ajuste de EV por tipo de apuesta:
      - ML / Spread: descuento sobre el equipo apostado (igual que antes).
      - Over: usa la nueva probabilidad ajustada del modelo (capa 2).
      - Under: lesiones favorecen el Under → no penalizar, actualizar probabilidad.
    """
    from scipy.stats import norm as _norm

    # ── Construir mapa jugador → stats ───────────────────────────────────
    player_map: dict[str, dict] = {}
    for p in home_players + away_players:
        player_map[p["player_name"].lower()] = p

    def _find_player(inj_name: str):
        low = inj_name.lower()
        for key, p in player_map.items():
            if low in key or key in low:
                return p
        return None

    # ── CAPA 1: Alertas ──────────────────────────────────────────────────
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

    # ── CAPA 2: Ajuste de scores proyectados ─────────────────────────────
    # Out = 100% de PPG perdido; Doubtful = 50%; Questionable = no ajustar
    _REPLACEMENT_RATE = 0.30   # otros jugadores absorben ~30% del PPG perdido
    _SCORE_FLOOR     = 0.75    # nunca reducir más del 25% del score base

    ppg_lost_home = sum(
        a["ppg"] * (1.0 if "out" in a["status"].lower() else 0.5)
        for a in alerts
        if a["team"] == analysis.home_team
        and ("out" in a["status"].lower() or "doubtful" in a["status"].lower())
    )
    ppg_lost_away = sum(
        a["ppg"] * (1.0 if "out" in a["status"].lower() else 0.5)
        for a in alerts
        if a["team"] == analysis.away_team
        and ("out" in a["status"].lower() or "doubtful" in a["status"].lower())
    )

    probs = analysis.probabilities
    orig_total = probs.home_score + probs.away_score
    adj_home = probs.home_score
    adj_away = probs.away_score
    scores_adjusted = False

    if ppg_lost_home >= 5.0:
        net_loss = ppg_lost_home * (1.0 - _REPLACEMENT_RATE)
        adj_home = max(probs.home_score - net_loss, probs.home_score * _SCORE_FLOOR)
        scores_adjusted = True

    if ppg_lost_away >= 5.0:
        net_loss = ppg_lost_away * (1.0 - _REPLACEMENT_RATE)
        adj_away = max(probs.away_score - net_loss, probs.away_score * _SCORE_FLOOR)
        scores_adjusted = True

    if scores_adjusted:
        adj_total = adj_home + adj_away
        std_total = (probs.std_home**2 + probs.std_away**2) ** 0.5
        market_total = probs.market_total or analysis.market_odds.get("total_line", adj_total)

        new_over = round(float(_norm.sf(market_total, loc=adj_total, scale=std_total)), 4)
        new_under = round(1.0 - new_over, 4)

        analysis.probabilities = dataclass_replace(
            probs,
            home_score=round(adj_home, 1),
            away_score=round(adj_away, 1),
            total_score=round(adj_total, 1),
            over_total=new_over,
            under_total=new_under,
        )
        probs = analysis.probabilities  # actualizar referencia

        loss_parts = []
        if ppg_lost_home >= 5.0:
            loss_parts.append(f"{analysis.home_team} −{ppg_lost_home:.0f}pts")
        if ppg_lost_away >= 5.0:
            loss_parts.append(f"{analysis.away_team} −{ppg_lost_away:.0f}pts")
        analysis.insights.insert(0,
            f"🏥 Total ajustado: {orig_total:.0f} → {adj_total:.0f} pts "
            f"({', '.join(loss_parts)})"
        )
        logger.info(
            f"[Lesiones] {analysis.home_team} vs {analysis.away_team}: "
            f"total {orig_total:.0f} → {adj_total:.0f} "
            f"| Over prob {probs.over_total:.3f}"
        )

    # ── CAPA 2.5: TIER_1 baja confirmada → −4% al total proyectado ─────────
    # La pérdida de eficiencia ofensiva de un TIER_1 (generador de juego único,
    # uso muy alto) tiende a ser mayor que su PPG sugiere. Se aplica una
    # reducción adicional fija del 4% al total, independiente del EV inicial.
    tier1_out_players = [
        a["player"]
        for a in alerts
        if "out" in a["status"].lower()
        and any(frag in a["player"].lower() for frag in _TIER_1_FRAGMENTS)
    ]
    if tier1_out_players:
        probs = analysis.probabilities
        pre_total = probs.home_score + probs.away_score
        t1_adj_factor = 1.0 - _TIER1_TOTAL_REDUCTION
        new_home = round(probs.home_score * t1_adj_factor, 1)
        new_away = round(probs.away_score * t1_adj_factor, 1)
        new_total = new_home + new_away
        std_total = (probs.std_home**2 + probs.std_away**2) ** 0.5
        market_total = probs.market_total or analysis.market_odds.get("total_line", new_total)
        new_over_t1 = round(float(_norm.sf(market_total, loc=new_total, scale=std_total)), 4)
        new_under_t1 = round(1.0 - new_over_t1, 4)
        analysis.probabilities = dataclass_replace(
            probs,
            home_score=new_home,
            away_score=new_away,
            total_score=round(new_total, 1),
            over_total=new_over_t1,
            under_total=new_under_t1,
        )
        analysis.insights.insert(0,
            f"⭐ TIER_1 baja: {', '.join(tier1_out_players)} — "
            f"total ajustado {pre_total:.0f} → {new_total:.0f} pts (−{_TIER1_TOTAL_REDUCTION:.0%})"
        )
        logger.info(
            f"[TIER_1] {analysis.home_team} vs {analysis.away_team}: "
            f"total {pre_total:.0f} → {new_total:.0f} | Over {new_over_t1:.3f}"
        )

    # ── CAPA 3: Ajuste de EV por tipo de apuesta ─────────────────────────
    if not analysis.best_bet or not (analysis.best_bet.is_value or analysis.best_bet.is_marginal):
        return

    sel = analysis.best_bet.selection

    # Over / Under — re-evaluar directamente con la nueva probabilidad del modelo
    if sel in ("Over", "Under"):
        if scores_adjusted:
            new_prob = probs.over_total if sel == "Over" else probs.under_total
            new_ev = (new_prob * analysis.best_bet.odds) - 1.0
            new_ev_pct = round(new_ev * 100, 2)
            new_is_value = bool(new_ev >= import_config.MIN_EV_THRESHOLD)
            new_is_marginal = bool(
                import_config.MARGINAL_EV_THRESHOLD <= new_ev < import_config.MIN_EV_THRESHOLD
                and not new_is_value
            )
            analysis.best_bet = dataclass_replace(
                analysis.best_bet,
                probability=round(new_prob, 4),
                ev=round(new_ev, 4),
                ev_percent=new_ev_pct,
                is_value=new_is_value,
                is_marginal=new_is_marginal,
            )
            if not new_is_value and not new_is_marginal:
                analysis.recommendation = "No apostar"
                analysis.confidence = "—"
            stars_all = [a["player"] for a in alerts if a["is_star"]]
            if stars_all:
                analysis.insights.insert(0,
                    f"⚠️ {sel} re-evaluado por bajas: "
                    + ", ".join(stars_all[:3])
                    + f" → EV {new_ev_pct:+.1f}%"
                )
        return  # Para Over/Under terminamos aquí

    # ML / Spread — descuento sobre el equipo apostado
    is_home_bet = sel in ("Home", "Spread Home")
    team_with_bet = analysis.home_team if is_home_bet else analysis.away_team

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
        new_ev = analysis.best_bet.ev * discount
        new_ev_pct = round(new_ev * 100, 2)
        analysis.best_bet = dataclass_replace(
            analysis.best_bet,
            ev=round(new_ev, 4),
            ev_percent=new_ev_pct,
            is_value=bool(new_ev >= import_config.MIN_EV_THRESHOLD),
        )
        if not analysis.best_bet.is_value:
            analysis.recommendation = "No apostar"
            analysis.confidence = "—"
        stars_out = [
            a["player"] for a in analysis.injury_alerts
            if a["team"] == team_with_bet and a["is_star"]
        ]
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

            # ── Blowout & Garbage Time detection ─────────────────────────
            probs = a.probabilities
            blowout_ctx = detect_blowout(
                probs.home_score, probs.away_score, probs.std_diff
            )
            a.blowout_context = blowout_ctx

            # Si hay blowout proyectado, ajustar prob de Over en la apuesta principal
            if blowout_ctx.is_blowout and a.best_bet and a.best_bet.selection == "Over":
                new_over = adjust_over_for_blowout(probs.over_total, blowout_ctx)
                if new_over != probs.over_total:
                    new_ev = (new_over * a.best_bet.odds) - 1.0
                    new_ev_pct = round(new_ev * 100, 2)
                    a.probabilities = dataclass_replace(
                        probs,
                        over_total=new_over,
                        under_total=round(1.0 - new_over, 4),
                    )
                    a.best_bet = dataclass_replace(
                        a.best_bet,
                        probability=round(new_over, 4),
                        ev=round(new_ev, 4),
                        ev_percent=new_ev_pct,
                        is_value=bool(new_ev >= config.MIN_EV_THRESHOLD),
                        is_marginal=bool(
                            config.MARGINAL_EV_THRESHOLD <= new_ev < config.MIN_EV_THRESHOLD
                        ),
                    )
                    a.insights.insert(0,
                        f"🏀 Over ajustado por blowout proyectado "
                        f"({blowout_ctx.projected_spread:.0f} pts, "
                        f"P={blowout_ctx.blowout_prob:.0%}) → Over prob "
                        f"{probs.over_total:.1%} → {new_over:.1%}"
                    )

            # ── Proyecciones por cuarto ───────────────────────────────────
            std_total = (probs.std_home**2 + probs.std_away**2) ** 0.5
            a.quarter_projections = _NormalModel().quarter_projections(
                probs.total_score, std_total, blowout_ctx
            )

            # Detect back-to-back teams for today's games
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
                blowout_ctx=blowout_ctx,
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
        "📋 /onces — Ver onces oficiales y pronóstico actualizado\n"
        "🔹 /analizar — Analizar La Liga (default)\n"
        "🔹 /roi — Consultar tu Bankroll y ROI histórico\n"
        "🔹 /ping — Verificar estado del motor\n\n"
        "El bot envía automáticamente los onces cuando se confirman (~60 min antes del partido)."
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
        keyboard.append([InlineKeyboardButton("🎯 Radar Props", callback_data="parlay")])
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


async def _lineup_monitor_task(app):
    """
    Tarea de fondo: comprueba onces oficiales cada 10 minutos.

    Cuando API-Football confirma los titulares de un partido de La Liga
    (normalmente ~60 min antes del pitido), re-analiza el pronóstico y
    envía el update al canal de Telegram y a todos los chats con análisis activo.
    """
    monitor = LineupMonitor()
    CHECK_INTERVAL = 10 * 60  # 10 minutos

    while True:
        try:
            loop = asyncio.get_running_loop()
            updates = await loop.run_in_executor(None, monitor.check_and_process)

            for upd in updates:
                msg = format_lineup_update(upd)

                # Enviar al canal principal
                if config.TELEGRAM_CHAT_ID:
                    try:
                        for chunk in _split_message(msg):
                            await app.bot.send_message(
                                chat_id=config.TELEGRAM_CHAT_ID,
                                text=chunk,
                                parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True,
                            )
                    except Exception as e:
                        logger.error(f"Error enviando update de onces al canal: {e}")

                # Enviar también a los chats que tienen análisis activo de La Liga
                for chat_id, cache in _jornada_cache.items():
                    if cache.get("sport") and cache["sport"].key != "laliga":
                        continue
                    if str(chat_id) == config.TELEGRAM_CHAT_ID:
                        continue  # ya enviado arriba
                    try:
                        for chunk in _split_message(msg):
                            await app.bot.send_message(
                                chat_id=chat_id,
                                text=chunk,
                                parse_mode=ParseMode.HTML,
                                disable_web_page_preview=True,
                            )
                    except Exception as e:
                        logger.error(f"Error enviando update de onces a chat {chat_id}: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error en tarea de onces: {e}", exc_info=True)

        await asyncio.sleep(CHECK_INTERVAL)


async def onces_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /onces — Comprueba manualmente si ya están publicados los onces de hoy.
    Si están disponibles, muestra el análisis actualizado con los titulares.
    """
    await update.message.reply_text("⏳ Consultando onces oficiales de La Liga...")

    try:
        monitor = LineupMonitor()
        loop = asyncio.get_running_loop()
        updates = await loop.run_in_executor(None, monitor.check_and_process)

        if not updates:
            await update.message.reply_html(
                "ℹ️ Todavía no hay onces confirmados para los próximos partidos de La Liga.\n"
                "Los titulares suelen publicarse ~60 minutos antes del partido."
            )
            return

        for upd in updates:
            msg = format_lineup_update(upd)
            for chunk in _split_message(msg):
                try:
                    await update.message.reply_html(chunk, disable_web_page_preview=True)
                except Exception:
                    await update.message.reply_text(
                        _strip_html(chunk), disable_web_page_preview=True
                    )

    except Exception as e:
        logger.error(f"Error en /onces: {e}", exc_info=True)
        await update.message.reply_text("❌ Error consultando onces. Revisa los logs.")


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
    application.add_handler(CommandHandler("onces", onces_command))

    # Callbacks de botones inline
    application.add_handler(CallbackQueryHandler(match_callback))

    logger.info("🚀 WinStake.ia Bot Daemon iniciado. Escuchando comandos de Telegram...")

    # Tareas de fondo: backtesting diario + monitor de onces
    async def post_init(app):
        asyncio.create_task(_daily_backtesting_task())
        asyncio.create_task(_lineup_monitor_task(app))
        logger.info("🔄 Monitor de onces activo — verificando cada 10 min")

    application.post_init = post_init
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
