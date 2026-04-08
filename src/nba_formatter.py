"""
WinStake.ia v2.4 — Formateador NBA para Telegram
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

VERSION = "v2.4"
MODEL_TAG = "Normal Distribution + DvP + Monte Carlo | Kelly ½"

# ── Límites de cuota combinada ────────────────────────────────
SAFE_ODDS_MIN   = 2.10
SAFE_ODDS_MAX   = 2.90
SAFE_ODDS_HARD  = 8.00   # nunca superar (drop legs si hace falta)
AGG_ODDS_MIN    = 4.50
AGG_ODDS_MAX    = 7.50
AGG_ODDS_HARD   = 9.00   # nunca superar


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


# ─────────────────────────────────────────────────────────────
# NBAFormatter
# ─────────────────────────────────────────────────────────────

class NBAFormatter:
    """Formatea análisis NBA para Telegram (WinStake.ia v2.3)."""

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
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
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
                lines.append(f"{dt.strftime('%d/%m/%Y %H:%M')} UTC")
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
                lines.append(
                    f"   {icon} <b>{al['player']}</b> ({al['team']}) — "
                    f"{al['status']}{ppg_str}"
                    + (f" — {al['detail']}" if al.get("detail") else "")
                )
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
            f"<i>🤖 WinStake.ia {VERSION} | Normal Distribution + DvP + Monte Carlo | "
            f"Kelly ½ | EV = (prob × cuota) − 1 | /roi</i>"
        )
        lines.append(f"\n{'=' * 30}")
        return "\n".join(lines)

    # ── Combinada ─────────────────────────────────────────────

    def format_parlay(self, analyses: list, roi_summary: dict = None) -> str:
        """
        Formato v2.4:
        🩹 Lesiones | 🛡️ SAFE (2 legs, 2.1-2.9x) | 💥 AGGRESSIVE (3-4 legs, 4.5-7.5x)
        🎯 Props (8-10, ≥5 cats) | 🔗 Correlated (3-5) | Footer exacto
        """
        lines = []
        lines.append("🎰 <b>COMBINADA RECOMENDADA — NBA</b>")
        lines.append(f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")

        # ── Sección de lesiones ───────────────────────────────
        # Recoger TODOS los lesionados (no solo estrellas), ordenados por PPG
        all_alerts = sorted(
            [al for a in analyses for al in getattr(a, "injury_alerts", [])],
            key=lambda x: x["ppg"], reverse=True,
        )
        # Deduplicar por nombre de jugador
        seen_players: set = set()
        unique_alerts = []
        for al in all_alerts:
            if al["player"] not in seen_players:
                unique_alerts.append(al)
                seen_players.add(al["player"])

        lines.append("🩹 <b>LESIONES CLAVE</b>")
        if unique_alerts:
            for al in unique_alerts[:6]:
                status_low = al["status"].lower()
                icon = "🔴" if "out" in status_low else ("🟠" if "doubtful" in status_low else "🟡")
                detail = f" ({al['detail']})" if al.get("detail") else ""
                ppg_str = f", {al['ppg']:.0f} PPG" if al["ppg"] > 0 else ""
                lines.append(
                    f"   {icon} <b>{al['player']}</b> ({al['team']}{ppg_str}) "
                    f"— {al['status']}{detail}"
                )
        else:
            lines.append("   Sin bajas confirmadas disponibles ahora.")
        lines.append("   <i>Sin API en tiempo real — verifica siempre antes de apostar.</i>")
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

        # ── Props Destacados (8-10, ≥5 categorías) ───────────
        if all_props:
            lines.append("🎯 <b>Props Destacados (Mejor EV — DvP)</b>")
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

        # ── Footer exacto v2.4 ────────────────────────────────
        roi_str = _roi_str(roi_summary)
        lines.append("─" * 32)
        lines.append("⚠️ <i>Cuotas estimadas. Verifica en tu casa de apuestas.</i>")
        lines.append("⚠️ <i>Lesiones pueden cambiar el value drásticamente.</i>")
        lines.append(
            f"<i>🤖 WinStake.ia {VERSION} | Normal Distribution + DvP + Monte Carlo | "
            f"Kelly ½ | EV = (prob × cuota) − 1 | Último ROI: {roi_str} (/roi)</i>"
        )
        return "\n".join(lines)

    # ── Resumen ejecutivo ─────────────────────────────────────

    def _format_summary(self, analyses: list) -> str:
        lines = ["\n<b>RESUMEN EJECUTIVO NBA</b>\n"]
        value_bets = sorted(
            [a for a in analyses if a.best_bet and a.best_bet.is_value],
            key=lambda a: a.best_bet.ev_percent, reverse=True,
        )
        no_bets = [a for a in analyses if not a.best_bet or not a.best_bet.is_value]

        if value_bets:
            lines.append("<b>Apuestas recomendadas:</b>\n")
            total_stake = 0.0
            for a in value_bets:
                b = a.best_bet
                stake = a.kelly.stake_units if a.kelly else 0
                total_stake += stake
                lines.append(f"- <b>{a.home_team} vs {a.away_team}</b>")
                lines.append(f"  {b.selection} @ {b.odds:.2f} (EV: {b.ev_percent:+.1f}%)")
                lines.append(f"  Stake: {stake:.1f}u | Conf: {a.confidence}")
                lines.append("")
            lines.append(f"Exposición total: {total_stake:.1f}u")
        else:
            lines.append("Sin apuestas con valor hoy.")

        if no_bets:
            lines.append(f"\nNo apostar ({len(no_bets)} partidos):")
            for a in no_bets:
                lines.append(f"   — {a.home_team} vs {a.away_team}")

        lines.append(f"\n{'=' * 30}")
        lines.append(f"\n<i>🤖 WinStake.ia {VERSION} | Análisis informativo. Apuesta responsable.</i>")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Helpers de combinada
# ─────────────────────────────────────────────────────────────

PRIORITY_CATS = ["pts", "reb", "ast", "pra", "sb", "fg3m"]


def _diversify_global_props(props: list, total: int = 10) -> list:
    """Garantiza ≥5 categorías distintas en el top. Reordena por confianza."""
    sorted_p = sorted(props, key=lambda x: x["confidence_score"], reverse=True)
    used_ids: set = set()
    selected: list = []

    # Fase 1: una rep por categoría prioritaria
    for cat in PRIORITY_CATS:
        if len(selected) >= 5:
            break
        for r in sorted_p:
            if id(r) not in used_ids and r["stat_key"] == cat:
                selected.append(r)
                used_ids.add(id(r))
                break

    # Fase 2: rellenar hasta total
    for r in sorted_p:
        if len(selected) >= total:
            break
        if id(r) not in used_ids:
            selected.append(r)
            used_ids.add(id(r))

    return sorted(selected, key=lambda x: x["confidence_score"], reverse=True)


def _build_safe_picks(value_bets: list, all_props: list) -> list[dict]:
    """
    Construye 2 picks SAFE (cuota objetivo 2.1-2.9x).
    Prioriza result bets EV+; si no hay suficientes usa top props.
    """
    picks = []

    for a, b in value_bets[:2]:
        conf_icon = {"Alta": "🟢", "Media": "🟡", "Baja": "🔴"}.get(a.confidence, "⚪")
        picks.append({
            "label": f"{b.selection} ({a.home_team} vs {a.away_team})",
            "odds": b.odds,
            "model_prob": b.probability,
            "ev_pct": b.ev_percent,
            "conf_icon": conf_icon,
            "type": "resultado",
        })

    # Completar con props si faltan legs
    for r in all_props:
        if len(picks) >= 2:
            break
        odds = r.get("estimated_odds", 1.85)
        picks.append({
            "label": f"{r['player']} Over {r['threshold']} {r['stat_label']} ({r['match']})",
            "odds": odds,
            "model_prob": r["confidence_score"],
            "ev_pct": None,
            "conf_icon": _conf_icon(r["confidence_score"]),
            "type": "prop",
        })

    return picks[:2]


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

    # Aplicar hard cap (nunca >8x)
    picks = _trim_to_hard_cap(picks, SAFE_ODDS_HARD)
    co = _combined_odds(picks)
    model_prob = _model_combined_prob(picks)

    # Nota de rango
    range_note = ""
    if co < SAFE_ODDS_MIN:
        range_note = " ⚠️ cuota baja (escasez de EV hoy)"
    elif co > SAFE_ODDS_MAX:
        range_note = " ⚠️ cuota ligeramente alta"

    lines = [f"🛡️ <b>SAFE (2 legs) — Bajo riesgo | Cuota objetivo 2.1x-2.9x</b>"]
    for i, p in enumerate(picks, 1):
        ev_str = f" | EV: {p['ev_pct']:+.1f}%" if p.get("ev_pct") is not None else ""
        odds_str = f"@ {p['odds']:.2f}" if p["type"] == "resultado" else f"@ ~{p['odds']:.2f} (est.)"
        lines.append(f"   {i}. <b>{p['label']}</b> {odds_str} {p['conf_icon']}{ev_str}")

    lines.append(
        f"   <b>Cuota combinada: ~{co:.2f}x</b>{range_note} | "
        f"Prob. estimada modelo: {model_prob:.0f}% | Stake: 2.0u"
    )
    lines.append("")
    return lines


def _build_aggressive_picks(value_bets: list, all_props: list) -> list[dict]:
    """
    Construye 3-4 picks AGGRESSIVE (cuota objetivo 4.5-7.5x).
    Mezcla resultado EV+ + props de distintos partidos.
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
        if len(picks) >= 4:
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
    if len(picks) < 3:
        for r in all_props:
            if len(picks) >= 3:
                break
            if id(r) not in {id(p) for p in picks}:
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

    return picks


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
            ev_str = f" | EV: {p['ev_pct']:+.1f}%" if p.get("ev_pct") is not None else ""
            lines.append(f"   {i}. <b>{p['label']}</b> @ {p['odds']:.2f} {p['conf_icon']}{ev_str}")

    lines.append(
        f"   <b>Cuota combinada: ~{co:.2f}x</b>{range_note} | "
        f"Prob. estimada modelo: {model_prob:.0f}% | Stake: 0.75u"
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
