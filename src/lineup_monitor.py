"""
WinStake.ia — Monitor de Onces Titulares (La Liga)

Detecta cuándo se publican los onces oficiales (~60 min antes del partido)
y re-analiza los pronósticos ajustando el modelo Poisson por ausencias clave.

Flujo:
  1. Cada 10 min comprueba si algún partido de La Liga empieza en < 90 min.
  2. Pide los onces a API-Football (fixtures/lineups).
  3. Cruza los titulares con la lista de goleadores del equipo.
  4. Si hay jugadores clave fuera del XI, ajusta lambda y recalcula EV.
  5. Formatea y devuelve el mensaje de actualización para Telegram.
"""

import logging
from dataclasses import replace as dataclass_replace
from datetime import datetime, timezone, timedelta
from typing import Optional

import config
from src.football_client import FootballClient
from src.odds_client import OddsClient
from src.analyzer import Analyzer, MatchAnalysis
from src.ev_calculator import EVCalculator
from src.poisson_model import PoissonModel, MatchProbabilities
from src.sports.config import LALIGA

logger = logging.getLogger(__name__)

# ── Parámetros de la ventana de monitoreo ───────────────────────────────────
LINEUP_WINDOW_MINS = 90      # Empezar a pedir onces 90 min antes del partido
LINEUP_STOP_MINS = 5         # No monitorear los 5 últimos minutos (partido iniciando)

# ── Umbrales de impacto ──────────────────────────────────────────────────────
MIN_GOALS_PER_90_KEY = 0.25  # Goles/90 mínimos para ser "jugador clave"
MIN_EV_DELTA_ALERT = 0.015   # 1.5% de cambio en EV para destacar el impacto
REPLACEMENT_RATE = 0.30      # El 30% de los goles del ausente los absorbe otro jugador
MAX_LAMBDA_REDUCTION = 0.30  # Nunca reducir el lambda más de un 30%


class LineupMonitor:
    """
    Monitor de alineaciones oficiales para La Liga.
    Mantiene estado de qué fixtures ya procesó para no re-enviar.
    """

    def __init__(self):
        self._football_client = FootballClient()
        self._ev_calculator = EVCalculator()
        # fixture_id → True cuando ya enviamos el update
        self._processed: set[int] = set()

    # ── API pública ──────────────────────────────────────────────────────────

    def check_and_process(self) -> list[dict]:
        """
        Comprueba onces para partidos dentro de la ventana de tiempo.
        Devuelve lista de dicts con el resultado del análisis por cada partido
        donde se han confirmado onces y aún no se habían procesado.
        """
        updates = []

        matches_in_window = self._get_matches_in_window()
        if not matches_in_window:
            return []

        today_fixtures = self._football_client.get_today_fixtures()
        if not today_fixtures:
            logger.debug("No se encontraron fixtures de La Liga hoy en API-Football")
            return []

        scorers = self._football_client.get_top_scorers()
        standings = self._football_client.get_standings()

        for match in matches_in_window:
            fixture = self._find_fixture(match["home_team"], match["away_team"], today_fixtures)
            if not fixture:
                continue

            fid = fixture["fixture_id"]
            if fid in self._processed:
                continue

            lineups = self._football_client.get_fixture_lineups(fid)
            if not lineups:
                continue

            home_xi = lineups["home"]["startXI"]
            away_xi = lineups["away"]["startXI"]
            if len(home_xi) < 11 or len(away_xi) < 11:
                continue

            # Onces completos → analizar impacto
            self._processed.add(fid)

            update = self._build_update(
                match=match,
                lineups=lineups,
                scorers=scorers,
                standings=standings,
                fixture=fixture,
            )
            updates.append(update)
            logger.info(
                f"📋 Onces procesados: {match['home_team']} vs {match['away_team']} "
                f"| ausentes local={len(update['home_absent'])} "
                f"visit={len(update['away_absent'])} "
                f"| EV delta={update['ev_delta']:+.1%}"
            )

        return updates

    # ── Lógica interna ───────────────────────────────────────────────────────

    def _get_matches_in_window(self) -> list[dict]:
        """Filtra los próximos partidos de La Liga dentro de la ventana de monitoreo."""
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(minutes=LINEUP_WINDOW_MINS)
        cutoff = now + timedelta(minutes=LINEUP_STOP_MINS)

        odds_client = OddsClient(sport_config=LALIGA)
        upcoming = odds_client.get_upcoming_odds()

        matches = []
        for m in upcoming:
            ct = m.get("commence_time", "")
            if not ct:
                continue
            try:
                match_dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            if cutoff <= match_dt <= window_end:
                matches.append(m)

        return matches

    def _find_fixture(self, home: str, away: str, fixtures: list[dict]) -> Optional[dict]:
        """Busca el fixture correspondiente en API-Football (fuzzy match de nombres)."""
        home_l = home.lower()
        away_l = away.lower()

        for f in fixtures:
            fh = f["home_team"].lower()
            fa = f["away_team"].lower()
            if (home_l in fh or fh in home_l) and (away_l in fa or fa in away_l):
                return f

        # Segunda pasada: solo apellido/token
        for f in fixtures:
            fh = f["home_team"].lower()
            fa = f["away_team"].lower()
            home_token = home_l.split()[-1]
            away_token = away_l.split()[-1]
            if home_token in fh and away_token in fa:
                return f

        return None

    def _build_update(
        self,
        match: dict,
        lineups: dict,
        scorers: list[dict],
        standings: list[dict],
        fixture: dict,
    ) -> dict:
        """
        Construye el dict completo de actualización para un partido:
          - Onces titulares
          - Ausencias de jugadores clave detectadas
          - Análisis original (sin onces) y ajustado (con onces)
          - Deltas de lambda y EV
        """
        home = match["home_team"]
        away = match["away_team"]

        # ── Onces ────────────────────────────────────────────────────────────
        home_xi_names = [p["name"] for p in lineups["home"]["startXI"]]
        away_xi_names = [p["name"] for p in lineups["away"]["startXI"]]

        # ── Goleadores por equipo ─────────────────────────────────────────────
        home_scorers = [s for s in scorers if _team_match(s["team_name"], home)]
        away_scorers = [s for s in scorers if _team_match(s["team_name"], away)]

        # ── Detectar ausencias clave ──────────────────────────────────────────
        home_absent = _find_absent_key_players(home_scorers, home_xi_names)
        away_absent = _find_absent_key_players(away_scorers, away_xi_names)

        # ── Análisis original (sin ajuste de onces) ───────────────────────────
        analyzer = Analyzer(sport_config=LALIGA)
        analyzer.calibrate_from_standings(standings)

        home_stats = self._football_client.find_team_in_standings(home, standings)
        away_stats = self._football_client.find_team_in_standings(away, standings)

        match_scorers = self._football_client.get_players_for_match(home, away, scorers)
        mid = match.get("id", f"{home}_{away}")

        original = analyzer.analyze_match(
            home_team=home,
            away_team=away,
            odds=match["avg_odds"],
            home_stats=home_stats,
            away_stats=away_stats,
            commence_time=match.get("commence_time", ""),
            match_id=mid,
            scorers=match_scorers,
        )

        # ── Ajustar lambdas por ausencias ─────────────────────────────────────
        orig_lh = original.probabilities.lambda_home
        orig_la = original.probabilities.lambda_away

        adj_lh = _apply_absence_factor(orig_lh, home_absent)
        adj_la = _apply_absence_factor(orig_la, away_absent)

        # ── Re-calcular probabilidades Poisson ───────────────────────────────
        poisson = PoissonModel()
        new_probs_base = poisson.poisson_probabilities(adj_lh, adj_la)

        # Conservar corners/tarjetas/xG del análisis original; solo actualizar goles
        new_probs = dataclass_replace(
            original.probabilities,
            lambda_home=adj_lh,
            lambda_away=adj_la,
            home_win=new_probs_base.home_win,
            draw=new_probs_base.draw,
            away_win=new_probs_base.away_win,
            over_25=new_probs_base.over_25,
            under_25=new_probs_base.under_25,
            over_15=new_probs_base.over_15,
            under_15=new_probs_base.under_15,
            over_35=new_probs_base.over_35,
            under_35=new_probs_base.under_35,
            btts_yes=new_probs_base.btts_yes,
            btts_no=new_probs_base.btts_no,
            double_chance_1x=new_probs_base.double_chance_1x,
            double_chance_x2=new_probs_base.double_chance_x2,
            double_chance_12=new_probs_base.double_chance_12,
        )

        # ── Re-calcular EV ────────────────────────────────────────────────────
        new_ev_results = self._ev_calculator.calculate_ev(new_probs, match["avg_odds"])
        new_best_bet = self._ev_calculator.find_best_bet(new_ev_results)

        # Kelly para la nueva apuesta
        new_kelly = None
        if new_best_bet and (new_best_bet.is_value or new_best_bet.is_marginal):
            new_kelly = self._ev_calculator.kelly_criterion(
                new_best_bet.probability, new_best_bet.odds
            )

        adjusted = dataclass_replace(
            original,
            probabilities=new_probs,
            ev_results=new_ev_results,
            best_bet=new_best_bet,
            kelly=new_kelly,
        )

        # ── Calcular deltas ───────────────────────────────────────────────────
        orig_ev = original.best_bet.ev if original.best_bet else 0.0
        new_ev = new_best_bet.ev if new_best_bet else 0.0
        ev_delta = new_ev - orig_ev

        return {
            "match": match,
            "home": home,
            "away": away,
            "home_xi": home_xi_names,
            "away_xi": away_xi_names,
            "home_formation": lineups["home"].get("formation", ""),
            "away_formation": lineups["away"].get("formation", ""),
            "home_coach": lineups["home"].get("coach", ""),
            "away_coach": lineups["away"].get("coach", ""),
            "home_absent": home_absent,
            "away_absent": away_absent,
            "original": original,
            "adjusted": adjusted,
            "ev_delta": ev_delta,
            "lambda_delta_home": adj_lh - orig_lh,
            "lambda_delta_away": adj_la - orig_la,
            "has_impact": bool(home_absent or away_absent),
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _team_match(name_a: str, name_b: str) -> bool:
    """Comprobación fuzzy de si dos nombres de equipo coinciden."""
    a, b = name_a.lower().strip(), name_b.lower().strip()
    return a in b or b in a


def _find_absent_key_players(team_scorers: list[dict], xi_names: list[str]) -> list[dict]:
    """
    Devuelve los goleadores clave del equipo que NO aparecen en el XI oficial.
    "Clave" = goals_per_90 >= MIN_GOALS_PER_90_KEY (default 0.25).
    """
    xi_lower = [n.lower() for n in xi_names]
    absent = []

    for scorer in team_scorers:
        if scorer["goals_per_90"] < MIN_GOALS_PER_90_KEY:
            continue

        full = scorer["player_name"].lower()
        # Intentar match por nombre completo o apellido
        tokens = full.split()
        last = tokens[-1] if tokens else full

        in_xi = any(
            full in xi or last in xi or xi in full
            for xi in xi_lower
        )
        if not in_xi:
            absent.append(scorer)

    return absent


def _apply_absence_factor(base_lambda: float, absent: list[dict]) -> float:
    """
    Reduce el lambda del equipo según los goleadores clave que no están en el XI.

    Fórmula:
      - Contribución del jugador = goals_per_90 / base_lambda (cap 50%)
      - Reducción neta = contribución × (1 - REPLACEMENT_RATE)
      - Total reducción máxima = MAX_LAMBDA_REDUCTION (30%)
    """
    if not absent or base_lambda <= 0:
        return base_lambda

    total_reduction = 0.0
    for p in absent:
        contribution = min(p["goals_per_90"] / max(base_lambda, 0.5), 0.50)
        net_reduction = contribution * (1.0 - REPLACEMENT_RATE)
        total_reduction += net_reduction

    total_reduction = min(total_reduction, MAX_LAMBDA_REDUCTION)
    new_lambda = base_lambda * (1.0 - total_reduction)
    return round(max(new_lambda, base_lambda * 0.70), 3)


# ── Formateador del mensaje de Telegram ─────────────────────────────────────

def format_lineup_update(update: dict) -> str:
    """Genera el mensaje HTML para Telegram con el once y el impacto en el pronóstico."""
    home = update["home"]
    away = update["away"]
    home_xi = update["home_xi"]
    away_xi = update["away_xi"]
    home_formation = update["home_formation"]
    away_formation = update["away_formation"]
    home_coach = update["home_coach"]
    away_coach = update["away_coach"]
    home_absent = update["home_absent"]
    away_absent = update["away_absent"]
    orig = update["original"]
    adj = update["adjusted"]

    lines = [
        "📋 <b>ONCES OFICIALES CONFIRMADOS</b>",
        f"⚽ <b>{home} vs {away}</b>",
        "",
    ]

    # ── Formaciones y entrenadores ────────────────────────────────────────────
    if home_formation or away_formation:
        lines.append(
            f"🔷 <b>Formaciones:</b> {home_formation or '?'} (Local) | {away_formation or '?'} (Visit.)"
        )
    if home_coach or away_coach:
        lines.append(f"👤 {home_coach or '—'} | {away_coach or '—'}")
    lines.append("")

    # ── Titulares ─────────────────────────────────────────────────────────────
    lines.append(f"<b>{home} (XI):</b>")
    lines += [f"  • {n}" for n in home_xi[:11]]
    lines.append("")

    lines.append(f"<b>{away} (XI):</b>")
    lines += [f"  • {n}" for n in away_xi[:11]]
    lines.append("")

    # ── Ausencias / rotaciones detectadas ────────────────────────────────────
    if home_absent:
        lines.append(f"⚠️ <b>Fuera del XI — {home}:</b>")
        for p in home_absent:
            lines.append(
                f"  • {p['player_name']}  ({p['goals_per_90']:.2f} G/90 · {p['goals']} goles)"
            )
        lines.append("")

    if away_absent:
        lines.append(f"⚠️ <b>Fuera del XI — {away}:</b>")
        for p in away_absent:
            lines.append(
                f"  • {p['player_name']}  ({p['goals_per_90']:.2f} G/90 · {p['goals']} goles)"
            )
        lines.append("")

    # ── Impacto en el modelo ──────────────────────────────────────────────────
    lines.append("📊 <b>Pronóstico actualizado con onces:</b>")

    orig_p = orig.probabilities
    adj_p = adj.probabilities

    # Lambdas
    dlh = update["lambda_delta_home"]
    dla = update["lambda_delta_away"]
    if abs(dlh) > 0.04 or abs(dla) > 0.04:
        lh_arrow = "▼" if dlh < 0 else "▲"
        la_arrow = "▼" if dla < 0 else "▲"
        lines.append(
            f"  λ {home}: {orig_p.lambda_home:.2f} → {adj_p.lambda_home:.2f} {lh_arrow}"
        )
        lines.append(
            f"  λ {away}: {orig_p.lambda_away:.2f} → {adj_p.lambda_away:.2f} {la_arrow}"
        )

    # Probabilidades 1X2
    lines.append(
        f"  1X2: {adj_p.home_win:.0%} / {adj_p.draw:.0%} / {adj_p.away_win:.0%}"
        + (f"  (antes: {orig_p.home_win:.0%}/{orig_p.draw:.0%}/{orig_p.away_win:.0%})"
           if abs(dlh) > 0.04 or abs(dla) > 0.04 else "")
    )

    # Mercados goles
    lines.append(
        f"  Over 2.5: {adj_p.over_25:.0%}  |  BTTS: {adj_p.btts_yes:.0%}"
    )

    # Best bet
    orig_bet = orig.best_bet
    adj_bet = adj.best_bet
    ev_delta = update["ev_delta"]

    lines.append("")
    if adj_bet and (adj_bet.is_value or adj_bet.is_marginal):
        delta_tag = f" ({ev_delta:+.1%})" if abs(ev_delta) >= MIN_EV_DELTA_ALERT else ""
        lines.append(
            f"✅ <b>Apuesta actualizada:</b> {adj_bet.selection} @ {adj_bet.odds:.2f}"
            f" | EV {adj_bet.ev_percent:+.1f}%{delta_tag}"
        )
        if adj.kelly:
            lines.append(f"   Kelly (½): {adj.kelly.stake_units:.2f}u")

        # Cambio de selección
        if orig_bet and orig_bet.selection != adj_bet.selection:
            lines.append(
                f"  ⚡ Selección cambió: <s>{orig_bet.selection}</s> → <b>{adj_bet.selection}</b>"
            )
        # EV que desaparece o cae a marginal
        if orig_bet and orig_bet.is_value and not adj_bet.is_value:
            lines.append("  ⚠️ El valor detectado antes del once ya no supera el umbral.")

    elif orig_bet and (orig_bet.is_value or orig_bet.is_marginal):
        lines.append(
            f"❌ <b>Valor eliminado por onces:</b> {orig_bet.selection} ya no tiene EV positivo."
        )
    else:
        lines.append("ℹ️ Sin apuesta de valor identificada (antes y después del once).")

    return "\n".join(lines)
