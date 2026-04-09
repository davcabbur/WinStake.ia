"""
WinStake.ia v3.1 — Formateador NBA para Telegram
Bot conservador: resumen ejecutivo solo ganadores/spread/totals, prob >52%, stake cap 2.5u, exposición 6-12u (hard cap 15u).
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

_SPAIN_TZ = ZoneInfo("Europe/Madrid")

logger = logging.getLogger(__name__)

VERSION = "v3.1"
MODEL_TAG = "Normal Distribution + DvP | Kelly ½ | Blend modelo-mercado aplicado"

# ── Límites de cuota combinada ────────────────────────────────
SAFE_ODDS_MIN   = 1.85
SAFE_ODDS_MAX   = 2.90
SAFE_ODDS_HARD  = 3.00   # nunca superar en SAFE (drop legs si hace falta)
AGG_ODDS_MIN    = 4.50
AGG_ODDS_MAX    = 7.50
AGG_ODDS_HARD   = 8.00   # nunca superar

# ── Límites v3.1 ──────────────────────────────────────────────
MAX_STAKE_PER_PICK          = 2.5   # máximo stake por pick individual
MAX_EXPOSURE_WARN           = 12.0  # aviso si exposición supera 12u (rango recomendado: 6-12u)
MAX_EXPOSURE_HARD           = 15.0  # hard cap — nunca superar
EV_MARKET_WARNING_THRESHOLD = 25.0  # EV > 25% → advertencia + stake reducido
EV_SUSPICIOUS_THRESHOLD     = 35.0  # EV > 35% → pick excluido del resumen
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
_PROP_SELECTIONS = {"pts", "reb", "ast", "3pm", "sb", "pra", "fg3m", "blk", "stl"}


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


def _build_correlated_picks(analyses: list) -> list[str]:
    """
    Genera sugerencias de correlated picks.
    Fuentes:
      1. Resultado EV+ del mismo equipo + prop de ese equipo (más confiable).
      2. Dos props del mismo partido con sinergia (ej. Over + alto anotador).
      3. Cualquier resultado + el prop de mayor confianza del partido.
    Devuelve al menos 3 sugerencias si hay datos suficientes.
    """
    picks = []

    for a in analyses:
        recs = getattr(a, "prop_recommendations", [])
        bb = a.best_bet

        # Tipo 1: resultado EV+ + mejor prop del mismo equipo
        if bb and bb.is_value and recs:
            sel = bb.selection
            if sel in ("Home", "Spread Home"):
                bet_team = a.home_team
            elif sel in ("Away", "Spread Away"):
                bet_team = a.away_team
            else:
                bet_team = None

            if bet_team:
                same = [r for r in recs if r["team"] == bet_team]
                if same:
                    top = same[0]
                    o1, o2 = bb.odds, top.get("estimated_odds", 1.85)
                    picks.append(
                        f"<b>{sel} {bet_team}</b> @ {o1:.2f} + "
                        f"<b>{top['player']} Over {top['threshold']} {top['stat_label']}</b> "
                        f"@ ~{o2:.2f} → ~{round(o1*o2,2):.2f}x"
                    )

        # Tipo 2: top prop del partido + segundo prop del partido (distinto equipo o categoría)
        if len(recs) >= 2:
            r1, r2 = recs[0], recs[1]
            # Solo si son de categorías distintas
            if r1["stat_key"] != r2["stat_key"] or r1["team"] != r2["team"]:
                o1, o2 = r1.get("estimated_odds", 1.85), r2.get("estimated_odds", 1.85)
                picks.append(
                    f"<b>{r1['player']} Over {r1['threshold']} {r1['stat_label']}</b> "
                    f"@ ~{o1:.2f} + "
                    f"<b>{r2['player']} Over {r2['threshold']} {r2['stat_label']}</b> "
                    f"@ ~{o2:.2f} → ~{round(o1*o2,2):.2f}x"
                    f" ({a.home_team} vs {a.away_team})"
                )

    # Tipo 3: fallback — si no llegamos a 3, añadir combinaciones cruzadas entre partidos
    if len(picks) < 3:
        all_top = []
        for a in analyses:
            recs = getattr(a, "prop_recommendations", [])
            if recs:
                all_top.append((recs[0], f"{a.home_team} vs {a.away_team}"))
        # Combinar pares de distintos partidos
        for i in range(len(all_top)):
            if len(picks) >= 5:
                break
            for j in range(i + 1, len(all_top)):
                r1, m1 = all_top[i]
                r2, m2 = all_top[j]
                if m1 == m2:
                    continue
                o1, o2 = r1.get("estimated_odds", 1.85), r2.get("estimated_odds", 1.85)
                picks.append(
                    f"<b>{r1['player']} Over {r1['threshold']} {r1['stat_label']}</b> ({m1.split(' vs')[0]}) "
                    f"@ ~{o1:.2f} + "
                    f"<b>{r2['player']} Over {r2['threshold']} {r2['stat_label']}</b> ({m2.split(' vs')[0]}) "
                    f"@ ~{o2:.2f} → ~{round(o1*o2,2):.2f}x"
                )

    # Deduplicar manteniendo orden
    seen: set = set()
    unique = []
    for p in picks:
        if p not in seen:
            unique.append(p)
            seen.add(p)
    return unique[:5]


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

            # Correlated pick del partido
            corr = _build_correlated_picks([a])
            if corr:
                lines.append(f"🔗 <b>Correlated:</b> {corr[0]}")
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

    # ── Combinada ─────────────────────────────────────────────

    def format_parlay(self, analyses: list, roi_summary: dict = None) -> str:
        """
        Formato v2.6:
        🩹 Lesiones + impacto contextual | 🛡️ SAFE (1-2 legs, 1.85-2.90x)
        💥 AGGRESSIVE (3 legs, 4.5-7.5x) | 🎯 Props (8-10, ≥6 cats) | 🔗 Correlated | Footer v2.6
        """
        lines = []
        lines.append("🎰 <b>COMBINADA RECOMENDADA — NBA</b>")
        lines.append(f"📅 {datetime.now(_SPAIN_TZ).strftime('%d/%m/%Y %H:%M')} (España)\n")

        # ── Sección de lesiones con impacto contextual ────────
        # Recoger lesiones de ESPN (todas, no solo estrellas), ordenadas por PPG
        all_injuries_raw: list[dict] = []
        for a in analyses:
            injuries = getattr(a, "injuries", {})
            props = getattr(a, "player_props", {})
            alerts = getattr(a, "injury_alerts", [])

            ppg_map: dict[str, float] = {}
            pos_map: dict[str, str] = {}
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
                # Impacto contextual
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

        # ── Recopilar datos ───────────────────────────────────
        value_bets = sorted(
            [(a, a.best_bet) for a in analyses if a.best_bet and a.best_bet.is_value],
            key=lambda x: x[1].ev_percent, reverse=True,
        )
        all_props: list[dict] = []
        for a in analyses:
            for r in getattr(a, "prop_recommendations", []):
                all_props.append({**r, "match": f"{a.home_team} vs {a.away_team}"})
        all_props = _diversify_global_props(all_props, total=10)

        # ── SAFE ─────────────────────────────────────────────
        safe_picks = _build_safe_picks(value_bets, all_props)
        lines += _format_safe_section(safe_picks)

        # ── AGGRESSIVE ───────────────────────────────────────
        agg_picks = _build_aggressive_picks(value_bets, all_props)
        lines += _format_aggressive_section(agg_picks)

        # ── Props Destacados (8-10, ≥6 categorías, max 2/jugador) ──
        if all_props:
            lines.append("🎯 <b>Props Destacados (DvP — ≥6 categorías)</b>")
            for r in all_props[:10]:
                conf_pct = int(r["confidence_score"] * 100)
                est_odds = r.get("estimated_odds", 1.85)
                lines.append(
                    f"{_conf_icon(r['confidence_score'])} <b>{r['player']}</b> "
                    f"({r.get('pos','?')}) — "
                    f"Over {r['threshold']} {r['stat_label']} @ ~{est_odds:.2f} [{conf_pct}%]"
                )
                lines.append(
                    f"   {_dvp_icon(r['dvp_factor'])} {r['match']} | "
                    f"Temp: {r['season_avg']} | Últ10: {_l10(r)}"
                )
            lines.append("")

        # ── Correlated Picks (3-5) ────────────────────────────
        corr_picks = _build_correlated_picks(analyses)
        if corr_picks:
            lines.append("🔗 <b>Correlated Picks Sugeridos</b>")
            for cp in corr_picks[:5]:
                lines.append(f"   • {cp}")
            lines.append("")
        elif not corr_picks and all_props:
            # Fallback: combinar los 2 mejores props de distintos partidos
            lines.append("🔗 <b>Correlated Picks Sugeridos</b>")
            lines.append("   • Sin correlaciones resultado+prop hoy. Ver Props Destacados arriba.")
            lines.append("")

        if not value_bets and not all_props:
            lines.append("❌ No hay picks con valor suficiente hoy.")

        # ── Footer v2.9 ───────────────────────────────────────
        roi_str = _roi_str(roi_summary)
        lines.append("─" * 32)
        lines.append("⚠️ <i>Cuotas estimadas. Verifica siempre en tu casa de apuestas.</i>")
        lines.append("⚠️ <i>Las lesiones pueden cambiar el value drásticamente. Revisa reportes oficiales.</i>")
        lines.append(
            f"<i>🤖 WinStake.ia {VERSION} | Normal Distribution + DvP | "
            f"Kelly ½ | EV = (prob × cuota) − 1 | Blend modelo-mercado aplicado | "
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
                b.is_value
                and b.probability >= MIN_PROB_THRESHOLD
                and 1.0 <= b.ev_percent <= EV_SUSPICIOUS_THRESHOLD
                and not ml_bloqueado
                and not ev_over_limit
                and oficiales < MAX_PICKS_SUMMARY
                and (MAX_EXPOSURE_HARD - total_stake) >= 0.5
            )

            if es_oficial:
                raw_stake = a.kelly.stake_units if a.kelly else 1.0
                stake = min(raw_stake, MAX_STAKE_PER_PICK)
                remaining = MAX_EXPOSURE_HARD - total_stake
                stake = max(min(stake, remaining), 0.5)
                stake = round(stake, 1)

                total_stake = round(total_stake + stake, 1)
                oficiales += 1

                raw_conf = getattr(a, "confidence", "Media")
                conf_label = str(raw_conf).capitalize()
                if b.selection in ("Home", "Away") and b.odds > 2.40:
                    conf_label = "Media"

                lines.append(
                    f"  {pick_desc} @ {b.odds:.2f} "
                    f"(Prob: {prob_pct}% | EV: {b.ev_percent:+.1f}%)"
                )
                lines.append(f"  Stake: {stake:.1f}u | Conf: {conf_label}")
            else:
                # Tendencia: EV siempre en primera línea, warning inline con Stake
                lines.append(
                    f"  {pick_desc} @ {b.odds:.2f} "
                    f"(Prob: {prob_pct}% | EV: {b.ev_percent:+.1f}%)"
                )
                warn_str = " ⚠️ Discrepancia excesiva con mercado" if ev_over_limit else ""
                lines.append(f"  Stake: 0u | Conf: Tendencia{warn_str}")

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
# Helpers de combinada
# ─────────────────────────────────────────────────────────────

PRIORITY_CATS = ["pts", "reb", "ast", "pra", "sb", "fg3m"]


def _diversify_global_props(props: list, total: int = 10) -> list:
    """Garantiza ≥6 categorías distintas en el top y max 2 props por jugador."""
    sorted_p = sorted(props, key=lambda x: x["confidence_score"], reverse=True)
    # Improvement 10: use (player, stat_key) tuple instead of id() for deduplication
    used_keys: set = set()
    player_count: dict = {}
    selected: list = []

    # Fase 1: una rep por categoría prioritaria (mínimo 6)
    for cat in PRIORITY_CATS:
        if len(selected) >= 6:
            break
        for r in sorted_p:
            key = (r["player"], r["stat_key"])
            if key not in used_keys and r["stat_key"] == cat:
                pname = r["player"]
                if player_count.get(pname, 0) < 2:
                    selected.append(r)
                    used_keys.add(key)
                    player_count[pname] = player_count.get(pname, 0) + 1
                    break

    # Fase 2: rellenar hasta total (max 2 por jugador)
    for r in sorted_p:
        if len(selected) >= total:
            break
        key = (r["player"], r["stat_key"])
        if key not in used_keys:
            pname = r["player"]
            if player_count.get(pname, 0) < 2:
                selected.append(r)
                used_keys.add(key)
                player_count[pname] = player_count.get(pname, 0) + 1

    return sorted(selected, key=lambda x: x["confidence_score"], reverse=True)


def _build_safe_picks(value_bets: list, all_props: list) -> list[dict]:
    """
    Construye 1-2 picks SAFE (cuota combinada 1.85x-2.90x).
    - Solo result bets con cuota individual 1.50-2.20 (favoritos limpios).
    - Si 2 legs superan 2.90x combinado, usa solo 1 (Single Pick SAFE).
    - Completa con props de alta confianza si no hay result bets.
    """
    candidates = []

    for a, b in value_bets:
        # Solo favoritos o ligeramente underdogs — cuotas muy altas elevan combinada
        if b.odds < 1.50 or b.odds > 2.20:
            continue
        conf_icon = {"Alta": "🟢", "Media": "🟡", "Baja": "🔴"}.get(a.confidence, "⚪")
        candidates.append({
            "label": f"{b.selection} ({a.home_team} vs {a.away_team})",
            "odds": b.odds,
            "model_prob": b.probability,
            "ev_pct": b.ev_percent,
            "conf_icon": conf_icon,
            "type": "resultado",
            "single": False,
        })

    # Completar con props de alta confianza (≥0.65) si faltan legs
    for r in all_props:
        if len(candidates) >= 2:
            break
        if r["confidence_score"] < 0.65:
            continue
        odds = r.get("estimated_odds", 1.85)
        candidates.append({
            "label": f"{r['player']} ({r.get('pos','?')}) Over {r['threshold']} {r['stat_label']} ({r['match']})",
            "odds": odds,
            "model_prob": r["confidence_score"],
            "ev_pct": None,
            "conf_icon": _conf_icon(r["confidence_score"]),
            "type": "prop",
            "single": False,
        })

    if not candidates:
        return []

    # Intentar 2 legs dentro del rango; si supera SAFE_ODDS_HARD → bajar a 1
    two = candidates[:2]
    if len(two) == 2 and _combined_odds(two) <= SAFE_ODDS_HARD:
        return two
    # Single Pick SAFE
    best = candidates[:1]
    best[0]["single"] = True
    return best


def _combined_odds(picks: list) -> float:
    total = 1.0
    for p in picks:
        total *= p["odds"]
    return round(total, 2)


def _trim_to_hard_cap(picks: list, cap: float) -> list:
    """Elimina el pick de menor confianza hasta que la cuota combinada ≤ cap."""
    p = list(picks)
    while len(p) > 1 and _combined_odds(p) > cap:
        # Quitar el de menor model_prob
        p.sort(key=lambda x: x.get("model_prob", 0), reverse=True)
        p = p[:-1]
    return p


def _format_safe_section(picks: list) -> list[str]:
    if not picks:
        return []

    is_single = picks[0].get("single", False) or len(picks) == 1
    co = _combined_odds(picks)
    model_prob = _model_combined_prob(picks)

    label_tag = "Single Pick SAFE ⚠️ escasez de picks conservadores" if is_single else "2 legs"
    lines = [f"🛡️ <b>SAFE ({label_tag}) — Bajo riesgo | Cuota objetivo 1.85x-2.90x</b>"]

    for i, p in enumerate(picks, 1):
        ev_str = ""
        if p.get("ev_pct") is not None:
            ev_str = f" | EV: {p['ev_pct']:+.1f}%"
            if p["ev_pct"] > EV_MARKET_WARNING_THRESHOLD:
                ev_str += " ⚠️ <i>Alta discrepancia con mercado</i>"
        odds_str = f"@ {p['odds']:.2f}" if p["type"] == "resultado" else f"@ ~{p['odds']:.2f} (est.)"
        lines.append(f"   {i}. <b>{p['label']}</b> {odds_str} {p['conf_icon']}{ev_str}")

    has_props = any(p["type"] == "prop" for p in picks)
    odds_display = f"~{co:.2f}x" if has_props else f"{co:.2f}x"

    range_note = ""
    if co < SAFE_ODDS_MIN:
        range_note = " ⚠️ cuota baja"
    elif co > SAFE_ODDS_MAX:
        range_note = " ⚠️ cuota en límite superior"

    lines.append(
        f"   <b>Cuota combinada: {odds_display}</b>{range_note} | "
        f"Prob. estimada modelo: {model_prob:.0f}% | Stake: 2.0u"
    )
    if has_props:
        lines.append("   ⚠️ <i>Cuotas de props estimadas. Confirma en tu casa.</i>")
    lines.append("")
    return lines


def _build_aggressive_picks(value_bets: list, all_props: list) -> list[dict]:
    """
    Construye exactamente 3 picks AGGRESSIVE (cuota objetivo 4.5-7.5x).
    Mezcla resultado EV+ + props de distintos partidos.
    Máximo 3 legs — nunca más.
    """
    picks = []
    used_matches: set = set()

    # Primer leg: mejor result bet
    for a, b in value_bets[:1]:
        mk = f"{a.home_team}_{a.away_team}"
        used_matches.add(mk)
        conf_icon = {"Alta": "🟢", "Media": "🟡", "Baja": "🔴"}.get(a.confidence, "⚪")
        picks.append({
            "label": f"{b.selection} ({a.home_team} vs {a.away_team})",
            "odds": b.odds,
            "model_prob": b.probability,
            "ev_pct": b.ev_percent,
            "conf_icon": conf_icon,
            "type": "resultado",
        })

    # Legs adicionales: props de partidos distintos, diversificando categorías
    used_cats: set = set()
    for r in all_props:
        if len(picks) >= 3:   # tope estricto en 3
            break
        home, away = r["match"].split(" vs ", 1)
        mk = f"{home}_{away}"
        if mk in used_matches:
            continue
        # Preferir categorías no usadas aún
        if r["stat_key"] in used_cats and len(picks) >= 2:
            continue
        used_matches.add(mk)
        used_cats.add(r["stat_key"])
        odds = r.get("estimated_odds", 1.85)
        picks.append({
            "label": f"{r['player']} Over {r['threshold']} {r['stat_label']} ({r['match']})",
            "odds": odds,
            "model_prob": r["confidence_score"],
            "ev_pct": None,
            "conf_icon": _conf_icon(r["confidence_score"]),
            "type": "prop",
            "conf_pct": int(r["confidence_score"] * 100),
        })

    # Si aún no llegamos a 3, añadir props del mismo partido
    # Improvement 10: use (player, stat_key) tuple instead of id() for deduplication
    if len(picks) < 3:
        used_prop_keys = {(p.get("player", p["label"]), p.get("stat_key", "")) for p in picks}
        for r in all_props:
            if len(picks) >= 3:
                break
            rkey = (r["player"], r["stat_key"])
            if rkey not in used_prop_keys:
                used_prop_keys.add(rkey)
                odds = r.get("estimated_odds", 1.85)
                picks.append({
                    "label": f"{r['player']} Over {r['threshold']} {r['stat_label']} ({r['match']})",
                    "odds": odds,
                    "model_prob": r["confidence_score"],
                    "ev_pct": None,
                    "conf_icon": _conf_icon(r["confidence_score"]),
                    "type": "prop",
                    "conf_pct": int(r["confidence_score"] * 100),
                    "player": r["player"],
                    "stat_key": r["stat_key"],
                })

    return picks[:3]  # garantía final: nunca más de 3


def _format_aggressive_section(picks: list) -> list[str]:
    if len(picks) < 2:
        return []

    # Aplicar hard cap (nunca >9x): quitar el menos confiable si es necesario
    picks = _trim_to_hard_cap(picks, AGG_ODDS_HARD)
    co = _combined_odds(picks)
    model_prob = _model_combined_prob(picks)
    n = len(picks)

    range_note = ""
    if co < AGG_ODDS_MIN:
        range_note = " ⚠️ cuota bajo objetivo"
    elif co > AGG_ODDS_MAX:
        range_note = " ⚠️ cuota alta, stake mínimo"

    lines = [f"💥 <b>AGGRESSIVE ({n} legs) — Riesgo medio | Cuota objetivo 4.5x-7.5x</b>"]
    for i, p in enumerate(picks, 1):
        if p["type"] == "prop":
            conf_str = f" [{p.get('conf_pct', 0)}%]"
            lines.append(f"   {i}. {p['label']} @ ~{p['odds']:.2f} (est.){conf_str}")
        else:
            ev_str = ""
            if p.get("ev_pct") is not None:
                ev_str = f" | EV: {p['ev_pct']:+.1f}%"
                if p["ev_pct"] > EV_MARKET_WARNING_THRESHOLD:
                    ev_str += " ⚠️ <i>Alta discrepancia con mercado</i>"
            lines.append(f"   {i}. <b>{p['label']}</b> @ {p['odds']:.2f} {p['conf_icon']}{ev_str}")

    lines.append(
        f"   <b>Cuota combinada: ~{co:.2f}x</b>{range_note} | "
        f"Prob. estimada modelo: {model_prob:.0f}% | Stake: 0.6u"
    )
    lines.append("")
    return lines


def _roi_str(roi_summary: dict | None) -> str:
    if not roi_summary or roi_summary.get("total_bets", 0) == 0:
        return "sin historial aún"
    roi = roi_summary.get("roi_percent", 0)
    n = roi_summary.get("total_bets", 0)
    sign = "+" if roi >= 0 else ""
    return f"{sign}{roi:.1f}% en {n} picks"
