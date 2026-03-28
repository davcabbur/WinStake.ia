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

    # Usamos HTML en vez de MarkdownV2 para evitar problemas de escape
    PARSE_MODE = "HTML"

    def format_full_report(self, analyses: list[MatchAnalysis]) -> list[str]:
        """
        Genera el reporte completo de la jornada.
        Retorna lista de mensajes (divididos si exceden 4096 chars).
        """
        messages = []

        # Header
        header = self._format_header(analyses)
        messages.append(header)

        # Un mensaje por partido
        for analysis in analyses:
            msg = self._format_match(analysis)
            messages.append(msg)

        # Resumen ejecutivo
        summary = self._format_summary(analyses)
        messages.append(summary)

        return messages

    def _format_header(self, analyses: list[MatchAnalysis]) -> str:
        """Genera header del reporte."""
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
        """Formatea un partido individual."""
        lines = []

        # Título
        lines.append(f"\n⚽ <b>{a.home_team} vs {a.away_team}</b>")
        if a.commence_time:
            try:
                dt = datetime.fromisoformat(a.commence_time.replace("Z", "+00:00"))
                lines.append(f"📅 {dt.strftime('%d/%m/%Y %H:%M')} UTC")
            except (ValueError, AttributeError):
                pass
        lines.append("")

        # 1. Probabilidades
        p = a.probabilities
        lines.append("<b>1. Probabilidades (Modelo Poisson)</b>")
        lines.append(f"   {a.home_team}: {p.home_win*100:.1f}%")
        lines.append(f"   Empate: {p.draw*100:.1f}%")
        lines.append(f"   {a.away_team}: {p.away_win*100:.1f}%")
        lines.append(f"   λ Local: {p.lambda_home:.2f} | λ Visitante: {p.lambda_away:.2f}")
        if p.xg_used:
            lines.append(f"   ⚡ xG: {a.home_team} {p.xg_home:.2f} — {a.away_team} {p.xg_away:.2f}")
        lines.append("")

        # 2. Cuotas
        odds = a.market_odds
        lines.append("<b>2. Cuotas de mercado</b>")
        lines.append(f"   {a.home_team}: {odds.get('home', '—')}")
        lines.append(f"   Empate: {odds.get('draw', '—')}")
        lines.append(f"   {a.away_team}: {odds.get('away', '—')}")
        if odds.get("over_25"):
            lines.append(f"   Over 2.5: {odds['over_25']} | Under 2.5: {odds.get('under_25', '—')}")
        lines.append("")

        # 3. Análisis de valor
        lines.append("<b>3. Análisis de valor (EV)</b>")
        for ev in a.ev_results:
            icon = "✅" if ev.is_value else "❌"
            lines.append(f"   {icon} {ev.selection}: EV = {ev.ev_percent:+.1f}%")
        lines.append("")

        # 4. Mejor apuesta
        lines.append("<b>4. Mejor apuesta</b>")
        if a.best_bet and a.best_bet.is_value:
            confidence_icon = {"Alta": "🟢", "Media": "🟡", "Baja": "🔴"}.get(a.confidence, "⚪")
            ev_icon = "🔥" if a.best_bet.ev_percent >= 15 else ("🟢" if a.best_bet.ev_percent >= 5 else "✅")
            
            lines.append(f"   📌 Selección: <b>{a.best_bet.selection}</b>")
            lines.append(f"   💰 Cuota: {a.best_bet.odds:.2f}")
            lines.append(f"   {ev_icon} EV: {a.best_bet.ev_percent:+.1f}%")
            lines.append(f"   {confidence_icon} Confianza: {a.confidence}")
        else:
            lines.append("   ❌ <b>No apostar</b> — Sin EV positivo suficiente")
        lines.append("")

        # 5. Stake (solo si hay best bet)
        if a.kelly and a.best_bet and a.best_bet.is_value:
            lines.append("<b>5. Stake recomendado</b>")
            lines.append(f"   Kelly completo: {a.kelly.kelly_full:.1f}%")
            lines.append(f"   Half-Kelly: {a.kelly.kelly_half:.1f}%")
            lines.append(f"   Stake: {a.kelly.stake_units:.1f} unidades")
            lines.append(f"   Riesgo: {a.kelly.risk_level}")
            lines.append("")

        # 6. Mercados adicionales
        lines.append("<b>6. Mercados adicionales</b>")

        # BTTS
        p = a.probabilities
        lines.append(f"   ⚽ BTTS Sí: {p.btts_yes*100:.0f}% | BTTS No: {p.btts_no*100:.0f}%")

        # Correct Score (top 3)
        if a.correct_scores:
            scores_str = " | ".join(
                f"{cs['score']} ({cs['percentage']}%)"
                for cs in a.correct_scores[:3]
            )
            lines.append(f"   🎯 Marcadores: {scores_str}")

        # Asian Handicap
        if a.asian_handicap and a.asian_handicap.get("best_line"):
            bl = a.asian_handicap["best_line"]
            lines.append(
                f"   📐 H.Asiático: {bl['label']} → "
                f"Local {bl['home_cover_pct']}% | Visitante {bl['away_cover_pct']}%"
            )
        lines.append("")

        # 7. Claves
        if a.insights:
            lines.append("<b>7. Claves 🧠</b>")
            for insight in a.insights[:4]:  # Max 4 insights
                lines.append(f"   • {insight}")

        lines.append(f"\n{'━' * 30}")

        return "\n".join(lines)

    def _format_summary(self, analyses: list[MatchAnalysis]) -> str:
        """Genera resumen ejecutivo con las mejores apuestas."""
        lines = []
        lines.append("\n🎯 <b>RESUMEN EJECUTIVO</b>\n")

        value_bets = [a for a in analyses if a.best_bet and a.best_bet.is_value]
        no_bets = [a for a in analyses if not a.best_bet or not a.best_bet.is_value]

        if value_bets:
            lines.append("<b>✅ Apuestas recomendadas:</b>\n")

            # Ordenar por EV descendente
            value_bets.sort(key=lambda x: x.best_bet.ev_percent, reverse=True)

            total_stake = 0
            for a in value_bets:
                b = a.best_bet
                confidence_icon = {"Alta": "🟢", "Media": "🟡", "Baja": "🔴"}.get(a.confidence, "⚪")
                ev_icon = "🔥" if b.ev_percent >= 15 else ("🟢" if b.ev_percent >= 5 else "✅")
                stake = a.kelly.stake_units if a.kelly else 0
                total_stake += stake
                lines.append(f"• <b>{a.home_team} vs {a.away_team}</b>")
                lines.append(f"  {ev_icon} {b.selection} @ {b.odds:.2f} (EV: {b.ev_percent:+.1f}%)")
                lines.append(f"  {confidence_icon} Stake: {stake:.1f}u | Conf: {a.confidence}")
                lines.append("")

            lines.append(f"\n💼 Exposición total: {total_stake:.1f} unidades / {self._bankroll_units()}")
        else:
            lines.append("❌ No se encontraron apuestas con valor esta jornada.")

        if no_bets:
            lines.append(f"\n⛔ No apostar ({len(no_bets)} partidos):")
            for a in no_bets:
                lines.append(f"   • {a.home_team} vs {a.away_team}")

        lines.append(f"\n{'━' * 30}")
        lines.append("\n⚠️ <i>Disclaimer: Análisis informativo. Apuesta responsable.</i>")
        lines.append("🤖 <i>Generado por WinStake.ia</i>")

        return "\n".join(lines)

    @staticmethod
    def _bankroll_units() -> str:
        """Retorna bankroll en formato legible."""
        import config
        return f"{config.BANKROLL_UNITS}u"
