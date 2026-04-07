"""
WinStake.ia — Formateador NBA para Telegram
Convierte NBAMatchAnalysis a mensajes HTML para Telegram.
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class NBAFormatter:
    """Formatea analisis de partidos NBA para Telegram."""

    PARSE_MODE = "HTML"

    def format_full_report(self, analyses: list) -> list[str]:
        """Genera el reporte completo del dia NBA."""
        messages = []
        messages.append(self._format_header(analyses))

        for analysis in analyses:
            messages.append(self._format_match(analysis))

        messages.append(self._format_summary(analyses))
        return messages

    def format_single_match(self, a) -> str:
        """Formatea un solo partido para respuesta inline."""
        return self._format_match(a)

    def _format_header(self, analyses: list) -> str:
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        n_matches = len(analyses)
        value_bets = sum(1 for a in analyses if a.best_bet and a.best_bet.is_value)

        return (
            f"<b>WINSTAKE.IA — NBA ANALYSIS</b>\n"
            f"Generado: {now}\n"
            f"{n_matches} partidos analizados\n"
            f"{value_bets} apuestas con valor detectadas\n"
            f"{'=' * 30}"
        )

    def _format_match(self, a) -> str:
        """Formatea un partido NBA individual."""
        lines = []

        # Titulo
        lines.append(f"\n<b>{a.home_team} vs {a.away_team}</b>")
        if a.commence_time:
            try:
                dt = datetime.fromisoformat(a.commence_time.replace("Z", "+00:00"))
                lines.append(f"{dt.strftime('%d/%m/%Y %H:%M')} UTC")
            except (ValueError, AttributeError):
                pass
        lines.append("")

        p = a.probabilities

        # 1. Moneyline
        lines.append("<b>1. Moneyline (H2H)</b>")
        lines.append(f"   {a.home_team}: {p.home_win*100:.1f}%")
        lines.append(f"   {a.away_team}: {p.away_win*100:.1f}%")
        lines.append(f"   Score esperado: {p.home_score:.0f} - {p.away_score:.0f}")
        lines.append("")

        # 2. Spread
        lines.append("<b>2. Spread</b>")
        if p.market_spread != 0:
            fav = a.home_team if p.spread < 0 else a.away_team
            lines.append(f"   Linea mercado: {a.home_team} {p.market_spread:+.1f}")
            lines.append(
                f"   Home cubre: {p.home_cover_prob*100:.1f}% | "
                f"Away cubre: {p.away_cover_prob*100:.1f}%"
            )
        lines.append(f"   Spread modelo: {p.spread:+.1f} pts")
        if hasattr(a, "spread_lines") and a.spread_lines:
            lines.append("   Lineas alternativas:")
            for sl in a.spread_lines:
                if abs(sl["spread"]) <= 8.5:
                    lines.append(
                        f"      {sl['label']}: "
                        f"Home {sl['home_cover_pct']}% | Away {sl['away_cover_pct']}%"
                    )
        lines.append("")

        # 3. Totals (Over/Under)
        lines.append("<b>3. Totals (Over/Under)</b>")
        lines.append(f"   Total esperado: {p.total_score:.0f} pts")
        if p.total_line > 0:
            lines.append(
                f"   O/U {p.total_line}: "
                f"{p.over_total*100:.0f}% / {p.under_total*100:.0f}%"
            )
        ou_odds = []
        if a.market_odds.get("over"):
            ou_odds.append(f"Over: {a.market_odds['over']}")
        if a.market_odds.get("under"):
            ou_odds.append(f"Under: {a.market_odds['under']}")
        if ou_odds:
            lines.append(f"   Cuotas: {' | '.join(ou_odds)}")
        if hasattr(a, "total_lines") and a.total_lines:
            lines.append("   Lineas alternativas:")
            for tl in a.total_lines:
                lines.append(
                    f"      {tl['line']}: "
                    f"Over {tl['over_pct']}% | Under {tl['under_pct']}%"
                )
        lines.append("")

        # 4. Analisis de Valor (EV)
        lines.append("<b>4. Analisis de Valor (EV)</b>")
        categories = {
            "Moneyline": ["Home", "Away"],
            "Spread": ["Spread Home", "Spread Away"],
            "Totals": ["Over", "Under"],
        }
        for cat_name, selections in categories.items():
            cat_evs = [ev for ev in a.ev_results if ev.selection in selections]
            if cat_evs:
                ev_strs = []
                for ev in cat_evs:
                    icon = "+" if ev.is_value else "-"
                    ev_strs.append(f"{icon}{ev.selection}: {ev.ev_percent:+.1f}%")
                lines.append(f"   <b>{cat_name}:</b> {' | '.join(ev_strs)}")
        lines.append("")

        # 5. Mejor Apuesta
        lines.append("<b>MEJOR APUESTA</b>")
        if a.best_bet and a.best_bet.is_value:
            confidence_icon = {"Alta": "+", "Media": "~", "Baja": "-"}.get(a.confidence, "?")
            ev_icon = "!" if a.best_bet.ev_percent >= 15 else ("+" if a.best_bet.ev_percent >= 5 else "ok")

            lines.append(f"   Seleccion: <b>{a.best_bet.selection}</b>")
            lines.append(f"   Cuota: {a.best_bet.odds:.2f}")
            lines.append(f"   [{ev_icon}] EV: {a.best_bet.ev_percent:+.1f}%")
            lines.append(f"   [{confidence_icon}] Confianza: {a.confidence}")

            if a.kelly:
                lines.append(
                    f"   Stake: {a.kelly.stake_units:.1f}u "
                    f"(Half-Kelly {a.kelly.kelly_half:.1f}%) | Riesgo: {a.kelly.risk_level}"
                )
        else:
            lines.append("   <b>No apostar</b> — Sin EV positivo suficiente")
        lines.append("")

        # 6. Claves
        if a.insights:
            lines.append("<b>Claves</b>")
            for insight in a.insights[:5]:
                lines.append(f"   - {insight}")

        lines.append(f"\n{'=' * 30}")
        return "\n".join(lines)

    def _format_summary(self, analyses: list) -> str:
        """Genera resumen ejecutivo con las mejores apuestas NBA."""
        lines = []
        lines.append("\n<b>RESUMEN EJECUTIVO NBA</b>\n")

        value_bets = [a for a in analyses if a.best_bet and a.best_bet.is_value]
        no_bets = [a for a in analyses if not a.best_bet or not a.best_bet.is_value]

        if value_bets:
            lines.append("<b>Apuestas recomendadas:</b>\n")
            value_bets.sort(key=lambda x: x.best_bet.ev_percent, reverse=True)

            total_stake = 0
            for a in value_bets:
                b = a.best_bet
                stake = a.kelly.stake_units if a.kelly else 0
                total_stake += stake
                lines.append(f"- <b>{a.home_team} vs {a.away_team}</b>")
                lines.append(f"  {b.selection} @ {b.odds:.2f} (EV: {b.ev_percent:+.1f}%)")
                lines.append(f"  Stake: {stake:.1f}u | Conf: {a.confidence}")
                lines.append("")

            lines.append(f"\nExposicion total: {total_stake:.1f} unidades")
        else:
            lines.append("No se encontraron apuestas con valor hoy.")

        if no_bets:
            lines.append(f"\nNo apostar ({len(no_bets)} partidos):")
            for a in no_bets:
                lines.append(f"   - {a.home_team} vs {a.away_team}")

        lines.append(f"\n{'=' * 30}")
        lines.append("\n<i>Disclaimer: Analisis informativo. Apuesta responsable.</i>")
        lines.append("<i>Generado por WinStake.ia</i>")

        return "\n".join(lines)
