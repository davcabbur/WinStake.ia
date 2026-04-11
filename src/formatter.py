"""
WinStake.ia — Formateador de Telegram
Convierte MatchAnalysis a mensajes formateados para Telegram (HTML).
"""

import logging
from datetime import datetime

from src.analyzer import MatchAnalysis, EVResult

logger = logging.getLogger(__name__)


class Formatter:
    """Formatea análisis de partidos para envío por Telegram."""

    PARSE_MODE = "HTML"

    def format_full_report(self, analyses: list[MatchAnalysis]) -> list[str]:
        """
        Genera el reporte completo de la jornada.
        Retorna lista de mensajes (divididos si exceden 4096 chars).
        """
        messages = []
        header = self._format_header(analyses)
        messages.append(header)

        for analysis in analyses:
            msg = self._format_match(analysis)
            messages.append(msg)

        return messages

    def format_single_match(self, a: MatchAnalysis) -> str:
        """Formatea un solo partido para envío como respuesta a un botón inline."""
        return self._format_match(a)

    def _format_header(self, analyses: list[MatchAnalysis]) -> str:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        n_matches = len(analyses)
        value_bets = sum(1 for a in analyses if a.best_bet and a.best_bet.is_value)

        return (
            f"🏆 <b>WINSTAKE.IA — ANÁLISIS LA LIGA</b>\n"
            f"📅 Generado: {now}\n"
            f"⚽ {n_matches} partidos analizados\n"
            f"🎯 {value_bets} apuestas con valor detectadas\n"
            f"{'━' * 30}"
        )

    def _format_match(self, a: MatchAnalysis) -> str:
        """Formatea un partido individual con TODOS los mercados."""
        lines = []

        # ── Título ──
        lines.append(f"\n⚽ <b>{a.home_team} vs {a.away_team}</b>")
        if a.commence_time:
            try:
                dt = datetime.fromisoformat(a.commence_time.replace("Z", "+00:00"))
                lines.append(f"📅 {dt.strftime('%d/%m/%Y %H:%M')} UTC")
            except (ValueError, AttributeError):
                pass
        lines.append("")

        # ── 1. Probabilidades 1X2 ──
        p = a.probabilities
        lines.append("<b>1. Resultado (1X2)</b>")
        lines.append(f"   {a.home_team}: {p.home_win*100:.1f}%")
        lines.append(f"   Empate: {p.draw*100:.1f}%")
        lines.append(f"   {a.away_team}: {p.away_win*100:.1f}%")
        lines.append(f"   λ Local: {p.lambda_home:.2f} | λ Visitante: {p.lambda_away:.2f}")
        if p.xg_used:
            lines.append(f"   ⚡ xG: {a.home_team} {p.xg_home:.2f} — {a.away_team} {p.xg_away:.2f}")
        lines.append("")

        # ── 2. Doble Oportunidad ──
        lines.append("<b>2. Doble Oportunidad</b>")
        lines.append(f"   1X ({a.home_team} o Empate): {p.double_chance_1x*100:.1f}%")
        lines.append(f"   X2 (Empate o {a.away_team}): {p.double_chance_x2*100:.1f}%")
        lines.append(f"   12 ({a.home_team} o {a.away_team}): {p.double_chance_12*100:.1f}%")
        # Mostrar cuotas si existen
        dc_odds = []
        if a.market_odds.get("double_chance_1x"):
            dc_odds.append(f"1X: {a.market_odds['double_chance_1x']}")
        if a.market_odds.get("double_chance_x2"):
            dc_odds.append(f"X2: {a.market_odds['double_chance_x2']}")
        if a.market_odds.get("double_chance_12"):
            dc_odds.append(f"12: {a.market_odds['double_chance_12']}")
        if dc_odds:
            lines.append(f"   💰 Cuotas: {' | '.join(dc_odds)}")
        lines.append("")

        # ── 3. Goles (Over/Under) ──
        lines.append("<b>3. Goles (Over/Under)</b>")
        lines.append(f"   O/U 1.5: {p.over_15*100:.0f}% / {p.under_15*100:.0f}%")
        lines.append(f"   O/U 2.5: {p.over_25*100:.0f}% / {p.under_25*100:.0f}%")
        lines.append(f"   O/U 3.5: {p.over_35*100:.0f}% / {p.under_35*100:.0f}%")
        ou_odds = []
        if a.market_odds.get("over_25"):
            ou_odds.append(f"O2.5: {a.market_odds['over_25']}")
        if a.market_odds.get("under_25"):
            ou_odds.append(f"U2.5: {a.market_odds['under_25']}")
        if ou_odds:
            lines.append(f"   💰 Cuotas: {' | '.join(ou_odds)}")
        lines.append("")

        # ── 4. BTTS ──
        lines.append("<b>4. Ambos Marcan (BTTS)</b>")
        lines.append(f"   Sí: {p.btts_yes*100:.0f}% | No: {p.btts_no*100:.0f}%")
        btts_odds = []
        if a.market_odds.get("btts_yes"):
            btts_odds.append(f"Sí: {a.market_odds['btts_yes']}")
        if a.market_odds.get("btts_no"):
            btts_odds.append(f"No: {a.market_odds['btts_no']}")
        if btts_odds:
            lines.append(f"   💰 Cuotas: {' | '.join(btts_odds)}")
        lines.append("")

        # ── 5. Marcadores exactos ──
        if a.correct_scores:
            lines.append("<b>5. Marcadores más probables</b>")
            for cs in a.correct_scores[:5]:
                lines.append(f"   {cs['score']}: {cs['percentage']}%")
            lines.append("")

        # ── 6. Corners ──
        if a.corners:
            c = a.corners
            lines.append("<b>6. Corners (estimación)</b>")
            lines.append(f"   {a.home_team}: ~{c['corners_home']:.0f} | {a.away_team}: ~{c['corners_away']:.0f} | Total: ~{c['total']:.0f}")
            lines.append(f"   Over 8.5: {c['over_85']*100:.0f}% | Over 9.5: {c['over_95']*100:.0f}% | Over 10.5: {c['over_105']*100:.0f}%")
            lines.append("")

        # ── 7. Tarjetas ──
        if a.cards:
            t = a.cards
            lines.append("<b>7. Tarjetas (estimación)</b>")
            lines.append(f"   {a.home_team}: ~{t['cards_home']:.1f} | {a.away_team}: ~{t['cards_away']:.1f} | Total: ~{t['total']:.1f}")
            lines.append(f"   Over 3.5: {t['over_35']*100:.0f}% | Over 4.5: {t['over_45']*100:.0f}% | Over 5.5: {t['over_55']*100:.0f}%")
            lines.append("")

        # ── 8. Goleadores ──
        if a.scorers and (a.scorers.get("home") or a.scorers.get("away")):
            lines.append("<b>8. Goleadores y Asistentes</b>")
            for side, label in [("home", a.home_team), ("away", a.away_team)]:
                players = a.scorers.get(side, [])
                if players:
                    lines.append(f"   <b>{label}:</b>")
                    for pl in players[:3]:
                        scorer_pct = pl.get("anytime_scorer_prob", 0) * 100
                        assist_pct = pl.get("anytime_assist_prob", 0) * 100
                        lines.append(
                            f"   • {pl['player_name']} — "
                            f"⚽ Anota: {scorer_pct:.0f}% | 🅰️ Asiste: {assist_pct:.0f}% "
                            f"({pl['goals']}G {pl['assists']}A en {pl['appearances']}P)"
                        )
            lines.append("")

        # ── 9. Hándicap Asiático ──
        if a.asian_handicap and a.asian_handicap.get("best_line"):
            bl = a.asian_handicap["best_line"]
            lines.append("<b>9. Hándicap Asiático</b>")
            lines.append(
                f"   Mejor línea: {bl['label']} → "
                f"Local {bl['home_cover_pct']}% | Visitante {bl['away_cover_pct']}%"
            )
            lines.append("")

        # ── 10. Picks por nivel de riesgo ──
        lines.extend(self._format_picks_by_risk(a))
        lines.append("")

        # ── 12. Claves ──
        if a.insights:
            lines.append("<b>🧠 Claves</b>")
            for insight in a.insights[:5]:
                lines.append(f"   • {insight}")

        lines.append(f"\n{'━' * 30}")
        return "\n".join(lines)

    # Grupos de riesgo: (etiqueta, cuota_min_incluida, cuota_max_excluida)
    _RISK_GROUPS = [
        ("🟢 SAFE",             1.80, 3.20),
        ("🟡 ARRIESGADA/SAFE",  3.20, 6.00),
        ("🔴 ARRIESGADA",       6.00, 999.0),
    ]
    _MAX_PICKS_PER_GROUP = 4

    def _format_picks_by_risk(self, a: MatchAnalysis) -> list[str]:
        """Genera picks del partido agrupados por nivel de riesgo (cuota)."""
        lines = []
        lines.append("<b>🎯 PICKS POR NIVEL DE RIESGO</b>")

        # Solo picks con cuota real disponible (la cuota proviene del mercado)
        candidates = [
            ev for ev in a.ev_results
            if ev.odds and ev.odds > 1.0
        ]

        any_group_has_picks = False
        for label, lo, hi in self._RISK_GROUPS:
            group = [ev for ev in candidates if lo <= ev.odds < hi]
            # Ordenar: primero los de mayor EV%
            group.sort(key=lambda x: x.ev_percent, reverse=True)
            group = group[:self._MAX_PICKS_PER_GROUP]

            range_str = f"{lo:.2f}–{hi:.2f}" if hi < 900 else f">{lo:.2f}"
            lines.append(f"\n   <b>{label}</b>  (cuota {range_str})")

            if not group:
                lines.append("   — Sin picks disponibles en este rango")
                continue

            any_group_has_picks = True
            for ev in group:
                if ev.is_value:
                    ev_icon = "✅"
                elif ev.is_marginal:
                    ev_icon = "🟡"
                elif ev.ev_percent >= 0:
                    ev_icon = "⚪"
                else:
                    ev_icon = "❌"
                lines.append(
                    f"   {ev_icon} <b>{ev.selection}</b> @ {ev.odds:.2f} "
                    f"— Prob: {ev.probability * 100:.0f}%  EV: {ev.ev_percent:+.1f}%"
                )

        if not any_group_has_picks:
            lines.append("\n   ⚠️ No hay cuotas de mercado disponibles para este partido")

        return lines

    @staticmethod
    def _bankroll_units() -> str:
        import config
        return f"{config.BANKROLL_UNITS}u"
