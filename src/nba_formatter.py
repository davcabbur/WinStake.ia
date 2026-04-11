"""
WinStake.ia v3.1 — Formateador NBA para Telegram
Bot conservador: resumen ejecutivo solo ganadores/spread/totals, prob >52%, stake cap 2.5u, exposición 6-12u (hard cap 15u).
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from src.nba_tiers import (
    get_team_tier,
    TIER_B_STAKE_CAP as _TIER_B_STAKE_CAP,
    TIER_B_LARGE_SPREAD_CAP as _TIER_B_LARGE_SPREAD_CAP,
    TIER_C_MIN_SPREAD as _TIER_C_MIN_SPREAD,
    TIER_C_TOTAL_BIAS_LINE as _TIER_C_TOTAL_BIAS_LINE,
    TIER_C_TOTALS_STAKE_CAP as _TIER_C_TOTALS_STAKE_CAP,
    TIER_A_SPECULATIVE_STAKE as _TIER_A_SPECULATIVE_STAKE,
)

_SPAIN_TZ = ZoneInfo("Europe/Madrid")

logger = logging.getLogger(__name__)

VERSION = "v3.1"
MODEL_TAG = "Normal Distribution + DvP | Kelly ½ | Blend modelo-mercado aplicado"

# ── Radar de Props Individuales — Umbrales v3.2 ────────────
RADAR_MIN_CONFIDENCE = 0.55   # confianza mínima para recomendar
RADAR_MIN_ODDS       = 1.70   # cuota estimada mínima
RADAR_MAX_ODDS       = 2.10   # cuota estimada máxima
RADAR_MAX_PER_PLAYER = 1      # máximo 1 prop por jugador
RADAR_MAX_PROPS      = 8      # máximo 8 props en el output

# ── Límites v3.1 ──────────────────────────────────────────────
MAX_STAKE_PER_PICK          = 2.5   # máximo stake por pick individual
MAX_EXPOSURE_WARN           = 10.0  # aviso si exposición supera 10u (rango recomendado: 6-10u)
MAX_EXPOSURE_HARD           = 12.0  # hard cap — nunca superar
EV_MARKET_WARNING_THRESHOLD = 25.0  # EV > 25% → advertencia + stake reducido
EV_SUSPICIOUS_THRESHOLD     = 35.0  # EV > 35% → Stake 0u, Sabiduría del Mercado > Modelo
LARGE_SPREAD_THRESHOLD      = 15.0  # Spread >15 pts → garbage time risk en abril
MAX_STAKE_LARGE_SPREAD      = 1.5   # Stake cap reducido para spreads masivos
MAX_PICKS_SUMMARY           = 6    # máximo de picks en el Resumen Ejecutivo
MAX_MONEYLINE_ODDS          = 2.50  # si CUALQUIER equipo supera esta cuota, ML bloqueado para el partido
MIN_PROB_THRESHOLD          = 0.52  # probabilidad mínima del modelo para recomendar

# ── Mapeo de selecciones a tipos de pick legibles ─────────────
_PICK_TYPE: dict[str, str] = {
    "Home":        "Ganador",
    "Away":        "Ganador",
    "Spread Home": "Spread",
    "Spread Away": "Spread",
    "Over":        "Totales",
    "Under":       "Totales",
}

# Selecciones consideradas props — NUNCA van en el Resumen Ejecutivo
_PROP_SELECTIONS = {"pts", "reb", "ast", "3pm", "fg3m"}


def _round_line(line: float) -> float:
    """Redondea líneas de spread/totales al .5 o .0 más cercano (estándar de mercado)."""
    return round(line * 2) / 2


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _conf_icon(conf: float) -> str:
    pct = conf * 100
    if pct >= 75:
        return "🔥"
    if pct >= 60:
        return "✅"
    return "🟡"


def _dvp_icon(factor: float) -> str:
    if factor > 1.05:
        return "⬆️"
    if factor < 0.95:
        return "⬇️"
    return "➡️"


def _l10(r: dict) -> str:
    v = r.get("l10_avg", 0)
    return f"{v:.1f}" if v > 0 else "N/D"


def _model_combined_prob(picks: list) -> float:
    """
    Probabilidad conjunta del modelo para una lista de picks.
    Para picks de resultado usa 'prob'; para props usa 'confidence_score'.
    """
    p = 1.0
    for pick in picks:
        p *= pick.get("model_prob", 0.5)
    return round(p * 100, 1)


def _filter_radar_props(all_props: list) -> list:
    """Filtra props según umbrales de Radar v3.2."""
    filtered = []
    seen_players = set()
    
    # Ordenar por confianza descendente
    sorted_props = sorted(all_props, key=lambda x: x.get("confidence_score", 0), reverse=True)
    
    for r in sorted_props:
        if len(filtered) >= RADAR_MAX_PROPS:
            break
        if r["player"] in seen_players:
            continue
        
        conf = r.get("confidence_score", 0)
        odds = r.get("estimated_odds", 0)
        
        if conf >= RADAR_MIN_CONFIDENCE and RADAR_MIN_ODDS <= odds <= RADAR_MAX_ODDS:
            filtered.append(r)
            seen_players.add(r["player"])
            
    return filtered


def _injury_impact_v26(status: str, ppg: float, pos: str) -> str:
    """
    Genera texto de impacto contextual para v2.6:
    combina status, PPG y posición para indicar qué mercados afecta.
    """
    status_low = status.lower()
    pos_up = pos.upper() if pos else ""
    is_out = "out" in status_low
    is_doubt = "doubtful" in status_low
    is_q = "questionable" in status_low or "day-to-day" in status_low

    if ppg >= 20.0:
        severity = "alto"
        markets = "spread y moneyline"
    elif ppg >= 12.0:
        severity = "medio"
        markets = "spread y props del equipo"
    elif ppg >= 6.0:
        severity = "bajo"
        markets = "props de rotación"
    else:
        return ""

    if pos_up in ("G", "PG", "SG"):
        prop_detail = "Impacto en props de AST y 3PM del equipo"
    elif pos_up in ("F", "SF", "PF"):
        prop_detail = "Impacto en props de PTS/PRA del equipo"
    elif pos_up in ("C",):
        prop_detail = "Impacto en props de REB del equipo"
    else:
        prop_detail = f"Impacto en props del equipo"

    if is_out:
        return f"Impacto {severity} en {markets}. {prop_detail}."
    elif is_doubt:
        return f"Impacto {severity} si no juega — {markets}. {prop_detail}."
    elif is_q:
        return f"Impacto {severity} si descansa — vigilar confirmación oficial."
    return ""


def _injury_impact_text(status: str, ppg: float) -> str:
    """Genera texto de impacto para lesiones según status y PPG."""
    status_low = status.lower()
    is_star = ppg >= 18.0
    if "out" in status_low:
        if is_star:
            return f"Impacto ALTO — baja estrella ({ppg:.0f} PPG). EV ajustado ×0.60"
        elif ppg >= 12.0:
            return f"Impacto MEDIO — jugador relevante ({ppg:.0f} PPG). Verificar suplente"
        return ""
    elif "doubtful" in status_low:
        if is_star:
            return f"Impacto ALTO si no juega — estrella ({ppg:.0f} PPG). EV ajustado ×0.80"
        return ""
    elif "questionable" in status_low:
        if is_star:
            return f"Impacto MODERADO — vigilar confirmación ({ppg:.0f} PPG). EV ajustado ×0.90"
        return ""
    return ""


# ─────────────────────────────────────────────────────────────
# NBAFormatter
# ─────────────────────────────────────────────────────────────

class NBAFormatter:
    """Formatea análisis NBA para Telegram (WinStake.ia v3.1)."""

    PARSE_MODE = "HTML"

    def format_full_report(self, analyses: list) -> list[str]:
        messages = [self._format_header(analyses)]
        for analysis in analyses:
            messages.append(self._format_match(analysis))
        messages.append(self._format_summary(analyses))
        return messages

    def format_single_match(self, a) -> str:
        return self._format_match(a)

    # ── Header ────────────────────────────────────────────────

    def _format_header(self, analyses: list) -> str:
        now = datetime.now(_SPAIN_TZ).strftime("%d/%m/%Y %H:%M")
        n = len(analyses)
        v = sum(1 for a in analyses if a.best_bet and a.best_bet.is_value)
        return (
            f"<b>WINSTAKE.IA {VERSION} — NBA ANALYSIS</b>\n"
            f"Generado: {now}\n"
            f"{n} partidos | {v} apuestas con valor\n"
            f"{'=' * 30}"
        )

    # ── Partido individual ────────────────────────────────────

    def _format_match(self, a) -> str:
        lines = []

        # Título
        lines.append(f"\n🏀 <b>{a.home_team} vs {a.away_team}</b>")
        if a.commence_time:
            try:
                dt = datetime.fromisoformat(a.commence_time.replace("Z", "+00:00"))
                dt_spain = dt.astimezone(_SPAIN_TZ)
                lines.append(f"{dt_spain.strftime('%d/%m/%Y %H:%M')} (España)")
            except (ValueError, AttributeError):
                pass
        lines.append("")

        p = a.probabilities

        # ── Alertas de lesiones (arriba del todo) ─────────────
        alerts = getattr(a, "injury_alerts", [])
        if alerts:
            lines.append("🚨 <b>Lesiones Relevantes</b>")
            for al in alerts:
                icon = "🔴" if "out" in al["status"].lower() else ("🟠" if "doubtful" in al["status"].lower() else "🟡")
                ppg_str = f" {al['ppg']:.0f} PPG" if al["ppg"] > 0 else ""
                impact = _injury_impact_text(al["status"], al["ppg"])
                lines.append(
                    f"   {icon} <b>{al['player']}</b> ({al['team']}) — "
                    f"{al['status']}{ppg_str}"
                    + (f" — {al['detail']}" if al.get("detail") else "")
                )
                if impact:
                    lines.append(f"      ↳ <i>{impact}</i>")
            lines.append("")

        # 1. Moneyline
        lines.append("<b>1. Moneyline</b>")
        lines.append(f"   {a.home_team}: {p.home_win*100:.1f}%")
        lines.append(f"   {a.away_team}: {p.away_win*100:.1f}%")
        lines.append(f"   Score esperado: {p.home_score:.0f} — {p.away_score:.0f}")
        lines.append("")

        # 2. Spread
        lines.append("<b>2. Spread</b>")
        if p.market_spread != 0:
            lines.append(f"   Línea mercado: {a.home_team} {p.market_spread:+.1f}")
            lines.append(
                f"   Home cubre: {p.home_cover_prob*100:.1f}% | "
                f"Away cubre: {p.away_cover_prob*100:.1f}%"
            )
        lines.append(f"   Spread modelo: {p.spread:+.1f} pts")
        if hasattr(a, "spread_lines") and a.spread_lines:
            for sl in a.spread_lines:
                if abs(sl["spread"]) <= 8.5:
                    lines.append(
                        f"   {sl['label']}: "
                        f"Home {sl['home_cover_pct']}% | Away {sl['away_cover_pct']}%"
                    )
        lines.append("")

        # 3. Totals
        lines.append("<b>3. Totals (O/U)</b>")
        lines.append(f"   Total esperado: {p.total_score:.0f} pts")
        if p.total_line > 0:
            lines.append(
                f"   O/U {p.total_line}: "
                f"{p.over_total*100:.0f}% / {p.under_total*100:.0f}%"
            )
        ou = []
        if a.market_odds.get("over"):
            ou.append(f"Over: {a.market_odds['over']}")
        if a.market_odds.get("under"):
            ou.append(f"Under: {a.market_odds['under']}")
        if ou:
            lines.append(f"   Cuotas: {' | '.join(ou)}")

        # Blowout warning en Totals
        blowout = getattr(a, "blowout_context", None)
        if blowout and blowout.is_blowout:
            fav_label = a.home_team if blowout.favored_team == "home" else a.away_team
            lines.append(
                f"   ⚠️ <i>Blowout proyectado ({blowout.projected_spread:.0f} pts, "
                f"P={blowout.blowout_prob:.0%}) — Over reducido por garbage time "
                f"Q4 ({fav_label} favorito)</i>"
            )
        lines.append("")

        # 3b. Proyecciones por cuarto
        quarters = getattr(a, "quarter_projections", [])
        if quarters:
            lines.append("<b>3b. Proyecciones por cuarto</b>")
            for q in quarters:
                q4_note = " ⚠️ <i>garbage time</i>" if q.get("blowout_q4") else ""
                lines.append(
                    f"   <b>{q['quarter']}</b>: {q['expected']:.0f} pts "
                    f"(O/U {q['line']}: {q['over_pct']:.0f}% / {q['under_pct']:.0f}%)"
                    f"{q4_note}"
                )
            lines.append("")

        # 4. EV
        lines.append("<b>4. Análisis de Valor (EV)</b>")
        for cat, sels in [("Moneyline", ["Home", "Away"]), ("Spread", ["Spread Home", "Spread Away"]), ("Totals", ["Over", "Under"])]:
            evs = [ev for ev in a.ev_results if ev.selection in sels]
            if evs:
                parts = [f"{'✅' if ev.is_value else '❌'} {ev.selection}: {ev.ev_percent:+.1f}%" for ev in evs]
                lines.append(f"   <b>{cat}:</b> {' | '.join(parts)}")
        lines.append("")

        # 5. Mejor apuesta
        lines.append("<b>⚡ Mejor Apuesta</b>")
        if a.best_bet and a.best_bet.is_value:
            conf_icon = {"Alta": "🟢", "Media": "🟡", "Baja": "🔴"}.get(a.confidence, "⚪")
            lines.append(f"   Selección: <b>{a.best_bet.selection}</b>")
            lines.append(f"   Cuota: {a.best_bet.odds:.2f} | EV: {a.best_bet.ev_percent:+.1f}%")
            lines.append(f"   {conf_icon} Confianza: {a.confidence}")
            if a.kelly:
                lines.append(
                    f"   Stake: {a.kelly.stake_units:.1f}u "
                    f"(Half-Kelly {a.kelly.kelly_half:.1f}%) | Riesgo: {a.kelly.risk_level}"
                )
        else:
            lines.append("   <b>No apostar</b> — Sin EV positivo")
        lines.append("")

        # 6. Últimos 10 partidos
        last10 = getattr(a, "team_last10", {})
        if last10.get("home") or last10.get("away"):
            lines.append("<b>6. Últimos 10 partidos</b>")
            for side, label in [("home", a.home_team), ("away", a.away_team)]:
                games = last10.get(side, [])
                if not games:
                    continue
                wins = sum(1 for g in games if g["win"])
                pts_avg = round(sum(g["pts"] for g in games) / len(games), 1)
                opp_avg = round(sum(g["opp_pts"] for g in games) / len(games), 1)
                recent = " ".join("✅" if g["win"] else "❌" for g in games[:10])
                lines.append(f"   <b>{label}</b> ({wins}W-{len(games)-wins}L) — {pts_avg:.0f}-{opp_avg:.0f}")
                lines.append(f"   {recent}")
            lines.append("")

        # 7. Jugadores clave
        props = getattr(a, "player_props", {})
        if props and (props.get("home") or props.get("away")):
            lines.append("<b>7. Jugadores Clave</b>")
            lines.append(f"   <code>{'Jugador':<22} {'PTS':>5} {'U10':>5} {'REB':>4} {'AST':>4} {'3PM':>4} {'STL':>4} {'BLK':>4}</code>")
            for side, label in [("home", a.home_team), ("away", a.away_team)]:
                players = props.get(side, [])[:7]
                if not players:
                    continue
                lines.append(f"   <b>{label}</b>")
                for pl in players:
                    name = pl["player_name"][:21]
                    lines.append(
                        f"   <code>{name:<22}"
                        f"{pl['pts_season']:>4.1f}/{pl.get('pts_l10',0):>4.1f}"
                        f" {pl['reb_season']:>4.1f}"
                        f" {pl['ast_season']:>4.1f}"
                        f" {pl['fg3m_season']:>4.1f}"
                        f" {pl.get('stl_season',0):>4.1f}"
                        f" {pl.get('blk_season',0):>4.1f}</code>"
                    )
            lines.append("")

        # 8. Props recomendados (DvP)
        recs = getattr(a, "prop_recommendations", [])
        if recs:
            lines.append("<b>🎯 Props Recomendados (DvP)</b>")
            lines.append("<i>Stats vs defensa rival por posición</i>")
            lines.append("")
            for r in recs:
                conf_pct = int(r["confidence_score"] * 100)
                pos_tag = f"({r.get('pos','?')})"
                est_odds = r.get("estimated_odds", 1.85)
                l10_display = _l10(r)
                lines.append(
                    f"{_conf_icon(r['confidence_score'])} <b>{r['player']}</b> {pos_tag} ({r['team']}) — "
                    f"<b>Over {r['threshold']} {r['stat_label']}</b> @ ~{est_odds:.2f} [{conf_pct}%]"
                )
                lines.append(
                    f"   {_dvp_icon(r['dvp_factor'])} Proy: {r['projected']} | "
                    f"Temp: {r['season_avg']} | Últ10: {l10_display}"
                )
                lines.append(f"   <i>{r['reason']}</i>")
                lines.append("")

        # 9. Claves del partido
        if a.insights:
            lines.append("<b>Claves</b>")
            for insight in a.insights[:6]:
                lines.append(f"   — {insight}")

        # Footer
        lines.append("")
        lines.append(
            f"<i>🤖 WinStake.ia {VERSION} | Normal Distribution + DvP | "
            f"Kelly ½ | EV = (prob × cuota) − 1 | Blend modelo-mercado aplicado | /roi</i>"
        )
        lines.append(f"\n{'=' * 30}")
        return "\n".join(lines)

    # ── Injury Report ─────────────────────────────────────────

    def format_injury_report(self, analyses: list) -> str | None:
        """
        Genera el Injury Report consolidado para los equipos que juegan hoy.
        Fuente: ESPN (via a.injuries) + PPG de a.player_props / a.injury_alerts.
        Retorna None si no hay lesiones relevantes.
        """
        STATUS_ICON = {
            "out": "🔴",
            "doubtful": "🟠",
            "questionable": "🟡",
            "day-to-day": "🟡",
        }
        RELEVANT = tuple(STATUS_ICON.keys())

        teams_seen: set[str] = set()
        sections: list[str] = []

        for a in analyses:
            injuries = getattr(a, "injuries", {})
            props = getattr(a, "player_props", {})
            alerts = getattr(a, "injury_alerts", [])

            # PPG lookup: prefer injury_alerts (already resolved), fallback player_props
            ppg_map: dict[str, float] = {}
            for side in ("home", "away"):
                for p in props.get(side, []):
                    ppg_map[p["player_name"].lower()] = p.get("pts_season", 0.0)
            for al in alerts:
                ppg_map[al["player"].lower()] = al.get("ppg", ppg_map.get(al["player"].lower(), 0.0))

            for side, team_name in [("home", a.home_team), ("away", a.away_team)]:
                if team_name in teams_seen:
                    continue
                teams_seen.add(team_name)

                team_injuries = injuries.get(side, [])
                relevant = [
                    inj for inj in team_injuries
                    if any(s in inj.get("status", "").lower() for s in RELEVANT)
                ]
                if not relevant:
                    continue

                lines: list[str] = [f"\n🏀 <b>{team_name}</b>"]
                for inj in relevant:
                    status_raw = inj.get("status", "")
                    player = inj.get("player", "")
                    detail = inj.get("detail", "")
                    pos = inj.get("position", "")
                    return_date = inj.get("return_date", "")

                    ppg = ppg_map.get(player.lower(), 0.0)
                    icon = next(
                        (v for k, v in STATUS_ICON.items() if k in status_raw.lower()),
                        "⚪",
                    )

                    name_part = f"<b>{player}</b>"
                    if pos:
                        name_part += f" <i>({pos})</i>"
                    if ppg >= 8.0:
                        name_part += f" — {ppg:.0f} PPG"

                    status_part = status_raw
                    if detail:
                        status_part += f" · {detail}"
                    if return_date:
                        status_part += f" · Ret: {return_date}"

                    lines.append(f"  {icon} {name_part}\n     <i>{status_part}</i>")

                sections.append("\n".join(lines))

        if not sections:
            return None

        header = f"🏥 <b>INJURY REPORT — {datetime.now(_SPAIN_TZ).strftime('%d/%m/%Y')}</b>"
        legend = "\n\n<i>🔴 Out  🟠 Doubtful  🟡 Day-to-Day / Questionable</i>"
        return header + "".join(sections) + legend

    # ── Combinada → Radar de Props Individuales ────────────

    def format_parlay(self, analyses: list, roi_summary: dict = None) -> str:
        """
        RADAR DE PROPS INDIVIDUALES v3.2:
        Solo props estadísticamente aislados (PTS/REB/AST/3PM).
        Filtro estricto: confidence ≥55%, cuota 1.70-2.10, max 1/jugador, max 8 total.
        Protocolo NO BET si no hay valor.
        """
        lines = []
        lines.append("🎯 <b>RADAR DE PROPS INDIVIDUALES — NBA</b>")
        lines.append(f"📅 {datetime.now(_SPAIN_TZ).strftime('%d/%m/%Y %H:%M')} (España)")
        lines.append("<i>(Solo recomendaciones simples. No combinar sin gestión de riesgo).</i>")
        lines.append("")

        # ── Sección de lesiones con impacto contextual ────────
        all_injuries_raw: list[dict] = []
        for a in analyses:
            injuries = getattr(a, "injuries", {})
            props = getattr(a, "player_props", {})
            alerts = getattr(a, "injury_alerts", [])

            ppg_map: dict[str, float] = {}
            for side in ("home", "away"):
                for p in props.get(side, []):
                    ppg_map[p["player_name"].lower()] = p.get("pts_season", 0.0)
            for al in alerts:
                ppg_map[al["player"].lower()] = al.get("ppg", ppg_map.get(al["player"].lower(), 0.0))

            for side, team_name in [("home", a.home_team), ("away", a.away_team)]:
                for inj in injuries.get(side, []):
                    status_low = inj.get("status", "").lower()
                    if not any(s in status_low for s in ("out", "doubtful", "questionable", "day-to-day")):
                        continue
                    player = inj.get("player", "")
                    ppg = ppg_map.get(player.lower(), 0.0)
                    pos = inj.get("position", "")
                    all_injuries_raw.append({
                        "player": player,
                        "team": team_name,
                        "status": inj.get("status", ""),
                        "detail": inj.get("detail", ""),
                        "pos": pos,
                        "ppg": ppg,
                    })

        # Deduplicar y ordenar por PPG
        seen_inj: set = set()
        unique_injuries = []
        for inj in sorted(all_injuries_raw, key=lambda x: x["ppg"], reverse=True):
            if inj["player"] not in seen_inj:
                unique_injuries.append(inj)
                seen_inj.add(inj["player"])

        lines.append("🩹 <b>LESIONES CLAVE</b>")
        if unique_injuries:
            for inj in unique_injuries[:8]:
                status_low = inj["status"].lower()
                icon = "🔴" if "out" in status_low else ("🟠" if "doubtful" in status_low else "🟡")
                ppg_str = f", {inj['ppg']:.0f} PPG" if inj["ppg"] >= 5.0 else ""
                pos_str = f" ({inj['pos']})" if inj["pos"] else ""
                detail_str = f" · {inj['detail']}" if inj.get("detail") else ""
                impact = _injury_impact_v26(inj["status"], inj["ppg"], inj.get("pos", ""))
                lines.append(
                    f"   {icon} <b>{inj['player']}</b>{pos_str} ({inj['team']}{ppg_str})"
                    f" — {inj['status']}{detail_str}"
                    + (f"\n      → {impact}" if impact else "")
                )
        else:
            lines.append(
                "   Varias questionable reportadas. "
                "Verifica reportes oficiales antes de apostar."
            )
        lines.append("")

        # ── Recopilar y filtrar props ───────────────────────
        all_props: list[dict] = []
        for a in analyses:
            for r in getattr(a, "prop_recommendations", []):
                all_props.append({**r, "match": f"{a.home_team} vs {a.away_team}"})

        filtered = _filter_radar_props(all_props)

        # ── RADAR DE PROPS INDIVIDUALES ─────────────────────
        if filtered:
            lines.append("🎯 <b>RADAR DE PROPS INDIVIDUALES</b>")
            lines.append("")
            for r in filtered:
                conf_pct = int(r["confidence_score"] * 100)
                est_odds = r.get("estimated_odds", 1.85)
                projected = r["projected"]
                threshold = r["threshold"]
                margin = round(projected - threshold, 1)
                ev_pct = round((r["confidence_score"] * est_odds - 1) * 100, 1)
                dvp_check = "✅" if r["dvp_factor"] > 1.05 else ("➖" if r["dvp_factor"] >= 0.95 else "❌")

                lines.append(
                    f"🔥 <b>{r['player']}</b> ({r.get('pos','?')}) — "
                    f"Over {r['threshold']} {r['stat_label']} @ ~{est_odds:.2f} (est.)"
                )
                lines.append(
                    f"   {_dvp_icon(r['dvp_factor'])} {r['match']}"
                )
                lines.append(
                    f"   📊 Prob: {conf_pct}% | EV: {ev_pct:+.1f}% | "
                    f"Margen: +{margin:.1f} (Proy: {projected:.1f} vs Línea: {threshold:.1f})"
                )
                l10_display = _l10(r)
                lines.append(
                    f"   💡 Temp: {r['season_avg']:.1f} | Últ10: {l10_display} | DvP Check: {dvp_check}"
                )
                lines.append("")
        else:
            # Protocolo NO BET
            lines.append("⛔️ Sin props con valor suficiente hoy. Protege tu bankroll.")
            lines.append("")

        # ── Footer v3.2 ───────────────────────────────────────
        roi_str = _roi_str(roi_summary)
        lines.append("─" * 32)
        lines.append("⚠️ <i>Cuotas estimadas. Verifica siempre en tu casa de apuestas.</i>")
        lines.append(
            f"<i>🤖 WinStake.ia {VERSION} | Normal Distribution + DvP | "
            f"Confidence ≥55% | Cuota 1.70-2.10 | "
            f"Último ROI: {roi_str} (/roi)</i>"
        )
        return "\n".join(lines)

    # ── Resumen ejecutivo v3.1 ────────────────────────────────

    def _format_summary(self, analyses: list) -> str:
        """
        RESUMEN EJECUTIVO v3.1:
        - Un pick por partido SIEMPRE (nunca "Sin recomendación clara").
        - PICK OFICIAL (con stake): prob >52%, EV 1–35%, ML odds ≤3.0.
        - TENDENCIA (stake 0u): no cumple requisitos para oficial.
        - EV >35% → Tendencia + "⚠️ Discrepancia excesiva con mercado".
        - Líneas redondeadas a .0 o .5 (estándar de mercado).
        - Labels: Ganador / Spread / Totales.
        - Stake máx 2.5u. Exposición máx 15u (aviso desde 12u). Máx 6 oficiales.
        """
        lines = ["\n<b>RESUMEN EJECUTIVO NBA</b>\n"]
        lines.append("<b>Apuestas recomendadas:</b>\n")

        total_stake = 0.0
        oficiales = 0

        for a in analyses:
            b = a.best_bet
            matchup = f"{a.home_team} vs {a.away_team}"
            lines.append(f"- <b>{matchup}</b>")

            # Fallback: si best_bet es None, usar el EV result con mayor prob disponible
            if b is None or _PICK_TYPE.get(b.selection) is None:
                ev_results = getattr(a, "ev_results", [])
                valid = [r for r in ev_results if _PICK_TYPE.get(r.selection)]
                if valid:
                    b = max(valid, key=lambda r: r.probability)
                else:
                    # Sin ningún dato útil — Tendencia forzada hacia local
                    lines.append("  Ganador: (modelo sin datos suficientes) @ N/D (Prob: N/D)")
                    lines.append("  Stake: 0u | Conf: Tendencia")
                    lines.append("")
                    continue

            # ── ¿Está el ML bloqueado para este partido? ──────────
            # Si CUALQUIER equipo tiene cuota ML > 2.50, Moneyline queda
            # completamente prohibido. Pivota ANTES de construir el pick.
            market = getattr(a, "market_odds", {})
            home_ml = market.get("home") or 0.0
            away_ml = market.get("away") or 0.0
            partido_ml_bloqueado = max(home_ml, away_ml) > MAX_MONEYLINE_ODDS

            if partido_ml_bloqueado and b.selection in ("Home", "Away"):
                # Pivote real: sustituir best_bet por el mejor Spread/Totales disponible
                ev_results = getattr(a, "ev_results", [])
                alternativas = [
                    r for r in ev_results
                    if r.selection in ("Spread Home", "Spread Away", "Over", "Under")
                ]
                if alternativas:
                    b = max(alternativas, key=lambda r: r.ev_percent)
                # Si no hay alternativas, b sigue siendo el ML pero irá como Tendencia

            ml_bloqueado = partido_ml_bloqueado and b.selection in ("Home", "Away")

            # ML No-Bet: cuota < 1.25 → payout tan bajo que no hay valor real
            ml_no_bet = b.selection in ("Home", "Away") and b.odds < 1.25

            # ── Tier classification (v3.3 Tactical Manager) ─────────────
            home_tier = get_team_tier(a.home_team)
            away_tier = get_team_tier(a.away_team)
            tier_a_in_match = home_tier == "A" or away_tier == "A"

            # Over → Under bias: total >235 + Tier C tankeando → preferir Under
            if (
                b.selection == "Over" and b.line is not None
                and b.line > _TIER_C_TOTAL_BIAS_LINE
                and (home_tier == "C" or away_tier == "C")
            ):
                _ev_inner = getattr(a, "ev_results", [])
                _under_r = next((r for r in _ev_inner if r.selection == "Under"), None)
                if _under_r and (_under_r.is_value or _under_r.is_marginal or _under_r.ev_percent > 0):
                    b = _under_r

            # Tier C never-bet: no apostar A FAVOR de equipos tankeando
            # Excepción: spread >20 pts (línea tan amplia que puede cubrirse)
            if b.selection in ("Home", "Away"):
                _bet_tier = home_tier if b.selection == "Home" else away_tier
                tier_c_block = (_bet_tier == "C")
            elif b.selection in ("Spread Home", "Spread Away"):
                _bet_tier = home_tier if b.selection == "Spread Home" else away_tier
                tier_c_block = (
                    _bet_tier == "C"
                    and (b.line is None or abs(b.line) <= _TIER_C_MIN_SPREAD)
                )
            else:
                tier_c_block = False

            prob_pct = round(b.probability * 100, 1)
            ev_over_limit = b.ev_percent > EV_SUSPICIOUS_THRESHOLD

            # ── Descripción del pick ──────────────────────────────
            if b.selection in ("Home", "Spread Home"):
                team = a.home_team
            elif b.selection in ("Away", "Spread Away"):
                team = a.away_team
            else:
                team = None

            if b.selection in ("Spread Home", "Spread Away") and b.line is not None:
                line_val = _round_line(b.line)
                pick_desc = f"Spread: {team} {line_val:+.1f}"
            elif b.selection in ("Home", "Away"):
                pick_desc = f"Ganador: {team}"
            elif b.line is not None:
                line_val = _round_line(b.line)
                direction = "Over" if b.selection == "Over" else "Under"
                pick_desc = f"Totales: {direction} {line_val}"
            else:
                direction = "Over" if b.selection == "Over" else "Under"
                pick_desc = f"Totales: {direction}"

            # ── Clasificar: PICK OFICIAL o TENDENCIA ─────────────
            es_oficial = (
                (b.is_value or b.is_marginal)   # EV ≥ 1% (marginal) o ≥ 3% (value)
                and b.probability >= MIN_PROB_THRESHOLD
                and 1.0 <= b.ev_percent <= EV_SUSPICIOUS_THRESHOLD
                and not ml_bloqueado
                and not ml_no_bet               # ML No-Bet: odds < 1.25
                and not tier_c_block            # Tier C: equipo tankeando
                and not ev_over_limit
                and oficiales < MAX_PICKS_SUMMARY
                and (MAX_EXPOSURE_HARD - total_stake) >= 0.5
            )

            if es_oficial:
                raw_stake = a.kelly.stake_units if a.kelly else 1.0
                stake = min(raw_stake, MAX_STAKE_PER_PICK)

                # Picks marginales (1-3% EV): stake máx 1.0u
                if b.is_marginal and not b.is_value:
                    stake = min(stake, 1.0)

                # ── Tier B stake cap: posibles descansos / rotaciones ────────
                if home_tier == "B" or away_tier == "B":
                    stake = min(stake, _TIER_B_STAKE_CAP)

                # ── Tier C + Totals: anotación errática → cap 1.5u ──────────
                # Un equipo tankeando puede salir con suplentes y hundir el Over
                # (o dispararlo sin defensa). El spread del partido ya está
                # desequilibrado; no merece exponer más de 1.5u en Totales.
                if (home_tier == "C" or away_tier == "C") and b.selection in ("Over", "Under"):
                    stake = min(stake, _TIER_C_TOTALS_STAKE_CAP)

                # ── Spread masivo (>15 pts): cap 1.5u por garbage time ──────
                # Solo aplica a picks de tipo Spread. En Totales, el garbage
                # time puede inflarte el Over (suplentes sin defensa anotan
                # mucho), por lo que no se penaliza el stake allí.
                _probs = a.probabilities
                _mkt_spread = abs(getattr(_probs, "market_spread", 0) or 0)
                _mdl_spread = abs(getattr(_probs, "spread", 0) or 0)
                _game_spread = _mkt_spread if _mkt_spread > 0 else _mdl_spread
                large_spread = (
                    b.selection in ("Spread Home", "Spread Away")
                    and _game_spread > LARGE_SPREAD_THRESHOLD
                )
                if large_spread:
                    stake = min(stake, MAX_STAKE_LARGE_SPREAD)

                # ── Tier B + spread masivo: rotaciones casi seguras → 0.5u ──
                # Si el partido está tan desequilibrado que el Tier B ya descansa
                # titulares, el spread se destruye en Q4. Doble penalización.
                if large_spread and (home_tier == "B" or away_tier == "B"):
                    stake = min(stake, _TIER_B_LARGE_SPREAD_CAP)

                remaining = MAX_EXPOSURE_HARD - total_stake
                stake = max(min(stake, remaining), 0.5)
                stake = round(stake, 1)

                total_stake = round(total_stake + stake, 1)
                oficiales += 1

                # Confianza: Moderada para picks marginales, Alta/Media para value
                if b.is_marginal and not b.is_value:
                    conf_label = "Moderada"
                else:
                    raw_conf = getattr(a, "confidence", "Media")
                    conf_label = str(raw_conf).capitalize()
                    if b.selection in ("Home", "Away") and b.odds > 2.40:
                        conf_label = "Media"

                lines.append(
                    f"  {pick_desc} @ {b.odds:.2f} "
                    f"(Prob: {prob_pct}% | EV: {b.ev_percent:+.1f}%)"
                )
                tier_notes = []
                if large_spread:
                    if home_tier == "B" or away_tier == "B":
                        tier_notes.append(f"⚠️ Tier B + spread masivo ({_game_spread:.0f} pts) — rotaciones + garbage time")
                    else:
                        tier_notes.append(f"⚠️ Spread masivo ({_game_spread:.0f} pts) — garbage time risk")
                if (home_tier == "C" or away_tier == "C") and b.selection in ("Over", "Under"):
                    tier_notes.append("⚠️ Tier C — totales erráticos (tanking)")
                tier_note_str = (" " + " | ".join(tier_notes)) if tier_notes else ""
                lines.append(f"  Stake: {stake:.1f}u | Conf: {conf_label}{tier_note_str}")
            else:
                # Tendencia: EV siempre en primera línea, warning inline con Stake
                lines.append(
                    f"  {pick_desc} @ {b.odds:.2f} "
                    f"(Prob: {prob_pct}% | EV: {b.ev_percent:+.1f}%)"
                )
                if ev_over_limit:
                    if tier_a_in_match:
                        # Tier A presente: motivación máxima → stake especulativo
                        _spec = _TIER_A_SPECULATIVE_STAKE
                        _remaining = MAX_EXPOSURE_HARD - total_stake
                        _spec = max(min(_spec, _remaining), 0.0)
                        if _spec > 0:
                            total_stake = round(total_stake + _spec, 1)
                        lines.append(
                            f"  Stake: {_spec:.1f}u | Conf: Especulativo "
                            f"💡 Tier A — EV >{EV_SUSPICIOUS_THRESHOLD:.0f}% + motivación máxima"
                        )
                    else:
                        # Tier B/C o sin clasificar: Sabiduría del Mercado
                        a.stake_zero_overheat = True
                        lines.append(
                            f"  Stake: 0u | Conf: Tendencia ⚠️ Protocolo Stake 0u: "
                            f"EV >{EV_SUSPICIOUS_THRESHOLD:.0f}% — "
                            "Sabiduría del Mercado > Cálculo del Modelo"
                        )
                elif ml_no_bet:
                    lines.append(
                        f"  Stake: 0u | Conf: Tendencia "
                        f"🚫 No Bet: ML cuota {b.odds:.2f} < 1.25 — payout sin valor real"
                    )
                elif tier_c_block:
                    lines.append(
                        "  Stake: 0u | Conf: Tendencia "
                        "⛔ Tier C — equipo tankeando (sin motivación)"
                    )
                else:
                    lines.append("  Stake: 0u | Conf: Tendencia")

            lines.append("")

        # ── Exposición total ──────────────────────────────────────
        if total_stake < 6.0:
            exp_level = "baja"
        elif total_stake <= MAX_EXPOSURE_WARN:
            exp_level = "moderada"
        else:
            exp_level = "alta"

        lines.append(
            f"⚠️ Exposición {exp_level} ({total_stake:.1f}u). "
            f"Gestiona tu bankroll con cuidado."
        )
        lines.append(f"\nExposición total: {total_stake:.1f}u")
        lines.append(f"\n{'=' * 30}")
        lines.append(f"🤖 WinStake.ia {VERSION} | Análisis informativo. Apuesta responsable.")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Helpers de Radar de Props
# ─────────────────────────────────────────────────────────────

# Categorías permitidas (solo props estadísticamente aislados)
RADAR_ALLOWED_CATS = {"pts", "reb", "ast", "fg3m"}


def _filter_radar_props(props: list) -> list:
    """
    Filtra props para el Radar de Props Individuales.
    Reglas estrictas:
      - Solo categorías PTS/REB/AST/3PM (no PRA, no S+B)
      - Confidence >= RADAR_MIN_CONFIDENCE (55%)
      - Cuota estimada entre RADAR_MIN_ODDS (1.70) y RADAR_MAX_ODDS (2.10)
      - Máximo 1 prop por jugador
      - Máximo 8 props total
      - Ordenados por confidence_score descendente
    """
    # Paso 1: filtrar por categoría, confianza y cuota
    valid = []
    for r in props:
        if r.get("stat_key") not in RADAR_ALLOWED_CATS:
            continue
        if r.get("confidence_score", 0) < RADAR_MIN_CONFIDENCE:
            continue
        odds = r.get("estimated_odds", 0)
        if odds < RADAR_MIN_ODDS or odds > RADAR_MAX_ODDS:
            continue
        valid.append(r)

    # Paso 2: ordenar por confianza descendente
    valid.sort(key=lambda x: x["confidence_score"], reverse=True)

    # Paso 3: máximo 1 prop por jugador
    selected: list = []
    seen_players: set = set()
    for r in valid:
        player = r["player"]
        if player in seen_players:
            continue
        seen_players.add(player)
        selected.append(r)
        if len(selected) >= RADAR_MAX_PROPS:
            break

    return selected


def _roi_str(roi_summary: dict | None) -> str:
    if not roi_summary or roi_summary.get("total_bets", 0) == 0:
        return "sin historial aún"
    roi = roi_summary.get("roi_percent", 0)
    n = roi_summary.get("total_bets", 0)
    sign = "+" if roi >= 0 else ""
    return f"{sign}{roi:.1f}% en {n} picks"

