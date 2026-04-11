"""
WinStake.ia — Monitor de Onces Titulares (La Liga)

Detecta cuándo se publican los onces oficiales (~60 min antes del partido)
y re-analiza los pronósticos ajustando el modelo Poisson por ausencias clave.

Flujo:
  1. Cada 10 min comprueba si algún partido de La Liga empieza en < 90 min.
  2. Pide los onces a API-Football (fixtures/lineups).
  3. Cruza los titulares con la lista de goleadores del equipo.
  4. Clasifica jugadores clave en "ausente total" o "en el banquillo".
     - Ausente total → penalización del 70% de su contribución al lambda.
     - En el banquillo → penalización del 50% (puede salir al 60' y resolver).
  5. Re-calcula Poisson + EV y genera mensaje Telegram con señal visual.
"""

import logging
from dataclasses import replace as dataclass_replace
from datetime import datetime, timezone, timedelta
from typing import Optional

import config
from src.football_client import FootballClient
from src.odds_client import OddsClient
from src.analyzer import Analyzer
from src.ev_calculator import EVCalculator
from src.poisson_model import PoissonModel
from src.sports.config import LALIGA

logger = logging.getLogger(__name__)

# ── Ventana de monitoreo ─────────────────────────────────────────────────────
LINEUP_WINDOW_MINS = 90   # Empezar a pedir onces 90 min antes del partido
LINEUP_STOP_MINS   = 5    # No monitorear los 5 últimos minutos (partido iniciando)

# ── Umbrales de impacto ──────────────────────────────────────────────────────
MIN_GOALS_PER_90_KEY  = 0.25  # G/90 mínimos para ser "jugador clave"
MIN_EV_DELTA_ALERT    = 0.015 # 1.5pp de cambio para activar señal visual

# ── Tasas de penalización sobre la contribución del jugador ausente ───────────
# Ausente total (ni siquiera en la lista):
#   contribución × 70%  →  el equipo solo recupera el 30%
ABSENT_PENALTY_RATE = 0.70

# En el banquillo (puede salir al 60-70'):
#   contribución × 50%  →  el equipo recupera el 50% (efecto estrella tardío)
BENCH_PENALTY_RATE  = 0.50

# Cap global: nunca reducir el lambda más de un 30%
MAX_LAMBDA_REDUCTION = 0.30


class LineupMonitor:
    """
    Monitor de alineaciones oficiales para La Liga.
    Mantiene estado de qué fixtures ya procesó para no re-enviar.
    """

    def __init__(self):
        self._football_client = FootballClient()
        self._ev_calculator = EVCalculator()
        self._processed: set[int] = set()   # fixture_ids ya enviados

    # ── API pública ──────────────────────────────────────────────────────────

    def check_and_process(self) -> list[dict]:
        """
        Comprueba onces para partidos dentro de la ventana de tiempo.
        Devuelve lista de updates (uno por partido con onces recién confirmados).
        """
        updates = []

        matches_in_window = self._get_matches_in_window()
        if not matches_in_window:
            return []

        today_fixtures = self._football_client.get_today_fixtures()
        if not today_fixtures:
            logger.debug("No se encontraron fixtures de La Liga hoy en API-Football")
            return []

        scorers   = self._football_client.get_top_scorers()
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

            self._processed.add(fid)

            upd = self._build_update(
                match=match,
                lineups=lineups,
                scorers=scorers,
                standings=standings,
            )
            updates.append(upd)
            logger.info(
                f"📋 Onces: {match['home_team']} vs {match['away_team']} "
                f"| ausentes local={len(upd['home_absent'])} visit={len(upd['away_absent'])} "
                f"| banquillo local={len(upd['home_bench'])} visit={len(upd['away_bench'])} "
                f"| EV delta={upd['ev_delta']:+.1%}"
            )

        return updates

    # ── Lógica interna ───────────────────────────────────────────────────────

    def _get_matches_in_window(self) -> list[dict]:
        now        = datetime.now(timezone.utc)
        window_end = now + timedelta(minutes=LINEUP_WINDOW_MINS)
        cutoff     = now + timedelta(minutes=LINEUP_STOP_MINS)

        odds_client = OddsClient(sport_config=LALIGA)
        upcoming    = odds_client.get_upcoming_odds()

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
        home_l, away_l = home.lower(), away.lower()

        for f in fixtures:
            fh, fa = f["home_team"].lower(), f["away_team"].lower()
            if (home_l in fh or fh in home_l) and (away_l in fa or fa in away_l):
                return f

        # Segunda pasada por token final (apellido del equipo)
        for f in fixtures:
            fh, fa = f["home_team"].lower(), f["away_team"].lower()
            if home_l.split()[-1] in fh and away_l.split()[-1] in fa:
                return f

        return None

    def _build_update(
        self,
        match: dict,
        lineups: dict,
        scorers: list[dict],
        standings: list[dict],
    ) -> dict:
        home = match["home_team"]
        away = match["away_team"]

        # Nombres del XI y banquillo
        home_xi_names  = [p["name"] for p in lineups["home"]["startXI"]]
        away_xi_names  = [p["name"] for p in lineups["away"]["startXI"]]
        home_sub_names = lineups["home"].get("substitutes", [])
        away_sub_names = lineups["away"].get("substitutes", [])

        # Goleadores por equipo
        home_scorers = [s for s in scorers if _team_match(s["team_name"], home)]
        away_scorers = [s for s in scorers if _team_match(s["team_name"], away)]

        # Clasificar: ausente total vs banquillo
        home_absent, home_bench = _classify_key_players(home_scorers, home_xi_names, home_sub_names)
        away_absent, away_bench = _classify_key_players(away_scorers, away_xi_names, away_sub_names)

        # Análisis original (modelo base sin ajuste de onces)
        analyzer = Analyzer(sport_config=LALIGA)
        analyzer.calibrate_from_standings(standings)

        home_stats   = self._football_client.find_team_in_standings(home, standings)
        away_stats   = self._football_client.find_team_in_standings(away, standings)
        match_scorers = self._football_client.get_players_for_match(home, away, scorers)
        mid          = match.get("id", f"{home}_{away}")

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

        # Lambdas ajustadas con las dos tasas
        orig_lh = original.probabilities.lambda_home
        orig_la = original.probabilities.lambda_away

        adj_lh = _apply_absence_factor(orig_lh, home_absent, home_bench)
        adj_la = _apply_absence_factor(orig_la, away_absent, away_bench)

        # Re-calcular Poisson
        poisson_model = PoissonModel()
        new_base = poisson_model.poisson_probabilities(adj_lh, adj_la)

        new_probs = dataclass_replace(
            original.probabilities,
            lambda_home=adj_lh,
            lambda_away=adj_la,
            home_win=new_base.home_win,
            draw=new_base.draw,
            away_win=new_base.away_win,
            over_25=new_base.over_25,
            under_25=new_base.under_25,
            over_15=new_base.over_15,
            under_15=new_base.under_15,
            over_35=new_base.over_35,
            under_35=new_base.under_35,
            btts_yes=new_base.btts_yes,
            btts_no=new_base.btts_no,
            double_chance_1x=new_base.double_chance_1x,
            double_chance_x2=new_base.double_chance_x2,
            double_chance_12=new_base.double_chance_12,
        )

        # Re-calcular EV y Kelly
        new_ev_results = self._ev_calculator.calculate_ev(new_probs, match["avg_odds"])
        new_best_bet   = self._ev_calculator.find_best_bet(new_ev_results)

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

        orig_ev  = original.best_bet.ev if original.best_bet else 0.0
        new_ev   = new_best_bet.ev       if new_best_bet      else 0.0
        ev_delta = new_ev - orig_ev

        return {
            "match":            match,
            "home":             home,
            "away":             away,
            "home_xi":          home_xi_names,
            "away_xi":          away_xi_names,
            "home_formation":   lineups["home"].get("formation", ""),
            "away_formation":   lineups["away"].get("formation", ""),
            "home_coach":       lineups["home"].get("coach", ""),
            "away_coach":       lineups["away"].get("coach", ""),
            "home_absent":      home_absent,
            "away_absent":      away_absent,
            "home_bench":       home_bench,
            "away_bench":       away_bench,
            "original":         original,
            "adjusted":         adjusted,
            "ev_delta":         ev_delta,
            "lambda_delta_home": adj_lh - orig_lh,
            "lambda_delta_away": adj_la - orig_la,
            "has_impact":       bool(home_absent or away_absent or home_bench or away_bench),
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _team_match(name_a: str, name_b: str) -> bool:
    a, b = name_a.lower().strip(), name_b.lower().strip()
    return a in b or b in a


def _player_in_list(player_name: str, name_list: list[str]) -> bool:
    """Comprueba si el jugador aparece en una lista de nombres (fuzzy)."""
    full   = player_name.lower()
    tokens = full.split()
    last   = tokens[-1] if tokens else full
    for n in name_list:
        nl = n.lower()
        if full in nl or last in nl or nl in full:
            return True
    return False


def _classify_key_players(
    team_scorers: list[dict],
    xi_names: list[str],
    sub_names: list[str],
) -> tuple[list[dict], list[dict]]:
    """
    Clasifica los goleadores clave del equipo que NO están en el XI titular en:
      - absent: no está ni en el XI ni en el banquillo  → penalización 70%
      - bench:  está en el banquillo                    → penalización 50%

    "Clave" = goals_per_90 >= MIN_GOALS_PER_90_KEY.
    """
    absent: list[dict] = []
    bench:  list[dict] = []

    for scorer in team_scorers:
        if scorer["goals_per_90"] < MIN_GOALS_PER_90_KEY:
            continue

        name = scorer["player_name"]
        if _player_in_list(name, xi_names):
            continue  # titular → sin penalización

        if _player_in_list(name, sub_names):
            bench.append(scorer)
        else:
            absent.append(scorer)

    return absent, bench


def _apply_absence_factor(
    base_lambda: float,
    absent: list[dict],
    bench: list[dict],
) -> float:
    """
    Ajusta el lambda del equipo por ausencias de jugadores clave.

    Rates:
      - Ausente total  → penalización = contribución × ABSENT_PENALTY_RATE (70%)
      - En el banquillo → penalización = contribución × BENCH_PENALTY_RATE  (50%)

    Cap: nunca reducir más del MAX_LAMBDA_REDUCTION (30%) del lambda base.
    """
    if (not absent and not bench) or base_lambda <= 0:
        return base_lambda

    total_reduction = 0.0

    for p in absent:
        contribution    = min(p["goals_per_90"] / max(base_lambda, 0.5), 0.50)
        total_reduction += contribution * ABSENT_PENALTY_RATE

    for p in bench:
        contribution    = min(p["goals_per_90"] / max(base_lambda, 0.5), 0.50)
        total_reduction += contribution * BENCH_PENALTY_RATE

    total_reduction = min(total_reduction, MAX_LAMBDA_REDUCTION)
    new_lambda      = base_lambda * (1.0 - total_reduction)
    return round(max(new_lambda, base_lambda * 0.70), 3)


# ── Formateador del mensaje de Telegram ─────────────────────────────────────

def format_lineup_update(update: dict) -> str:
    """
    Genera el mensaje HTML para Telegram.

    Secciones:
      1. Cabecera (equipos, formaciones, técnicos)
      2. Once titular de cada equipo
      3. Rotaciones detectadas (ausentes + banquillo)
      4. Impacto en el modelo (lambdas, probabilidades 1X2, O/U)
      5. Bloque EV visual: 🟢/🔴 antes→después + señal de acción
    """
    home         = update["home"]
    away         = update["away"]
    home_xi      = update["home_xi"]
    away_xi      = update["away_xi"]
    home_formation = update["home_formation"]
    away_formation = update["away_formation"]
    home_coach   = update["home_coach"]
    away_coach   = update["away_coach"]
    home_absent  = update["home_absent"]
    away_absent  = update["away_absent"]
    home_bench   = update["home_bench"]
    away_bench   = update["away_bench"]
    orig         = update["original"]
    adj          = update["adjusted"]
    ev_delta     = update["ev_delta"]

    lines = [
        "📋 <b>ONCES OFICIALES CONFIRMADOS</b>",
        f"⚽ <b>{home}  vs  {away}</b>",
        "",
    ]

    # ── 1. Formaciones / técnicos ─────────────────────────────────────────────
    if home_formation or away_formation:
        lines.append(
            f"🔷 <b>Sistema:</b> {home_formation or '?'} (local) "
            f"| {away_formation or '?'} (visit.)"
        )
    if home_coach or away_coach:
        lines.append(f"👤 {home_coach or '—'}  |  {away_coach or '—'}")
    lines.append("")

    # ── 2. Once titular ───────────────────────────────────────────────────────
    lines.append(f"<b>{home} (XI):</b>")
    lines += [f"  • {n}" for n in home_xi[:11]]
    lines.append("")

    lines.append(f"<b>{away} (XI):</b>")
    lines += [f"  • {n}" for n in away_xi[:11]]
    lines.append("")

    # ── 3. Rotaciones detectadas ──────────────────────────────────────────────
    has_rotations = home_absent or home_bench or away_absent or away_bench

    if home_absent:
        lines.append(f"🚫 <b>Ausente total — {home}:</b>")
        for p in home_absent:
            lines.append(
                f"  • {p['player_name']}  "
                f"({p['goals_per_90']:.2f} G/90 · {p['goals']} goles) "
                f"— <i>penalización λ ×70%</i>"
            )
        lines.append("")

    if home_bench:
        lines.append(f"💺 <b>En el banquillo — {home}:</b>")
        for p in home_bench:
            lines.append(
                f"  • {p['player_name']}  "
                f"({p['goals_per_90']:.2f} G/90 · {p['goals']} goles) "
                f"— <i>penalización λ ×50%</i>"
            )
        lines.append("")

    if away_absent:
        lines.append(f"🚫 <b>Ausente total — {away}:</b>")
        for p in away_absent:
            lines.append(
                f"  • {p['player_name']}  "
                f"({p['goals_per_90']:.2f} G/90 · {p['goals']} goles) "
                f"— <i>penalización λ ×70%</i>"
            )
        lines.append("")

    if away_bench:
        lines.append(f"💺 <b>En el banquillo — {away}:</b>")
        for p in away_bench:
            lines.append(
                f"  • {p['player_name']}  "
                f"({p['goals_per_90']:.2f} G/90 · {p['goals']} goles) "
                f"— <i>penalización λ ×50%</i>"
            )
        lines.append("")

    if not has_rotations:
        lines.append("✅ <i>Once confirmado sin rotaciones clave detectadas.</i>")
        lines.append("")

    # ── 4. Impacto en el modelo ───────────────────────────────────────────────
    lines.append("📊 <b>Modelo actualizado con onces:</b>")

    orig_p = orig.probabilities
    adj_p  = adj.probabilities
    dlh    = update["lambda_delta_home"]
    dla    = update["lambda_delta_away"]

    if abs(dlh) > 0.04:
        arrow = "▼" if dlh < 0 else "▲"
        lines.append(
            f"  λ {home}: {orig_p.lambda_home:.2f} → <b>{adj_p.lambda_home:.2f}</b> {arrow}"
        )
    if abs(dla) > 0.04:
        arrow = "▼" if dla < 0 else "▲"
        lines.append(
            f"  λ {away}: {orig_p.lambda_away:.2f} → <b>{adj_p.lambda_away:.2f}</b> {arrow}"
        )

    # 1X2 antes → después (solo si cambiaron)
    probs_changed = abs(dlh) > 0.04 or abs(dla) > 0.04
    if probs_changed:
        lines.append(
            f"  1X2 antes:  {orig_p.home_win:.0%} / {orig_p.draw:.0%} / {orig_p.away_win:.0%}"
        )
        lines.append(
            f"  1X2 ahora:  <b>{adj_p.home_win:.0%} / {adj_p.draw:.0%} / {adj_p.away_win:.0%}</b>"
        )
    else:
        lines.append(
            f"  1X2: {adj_p.home_win:.0%} / {adj_p.draw:.0%} / {adj_p.away_win:.0%}"
        )

    lines.append(
        f"  Over 2.5: <b>{adj_p.over_25:.0%}</b>  |  BTTS: <b>{adj_p.btts_yes:.0%}</b>"
    )
    lines.append("")

    # ── 5. Bloque EV visual ───────────────────────────────────────────────────
    orig_bet = orig.best_bet
    adj_bet  = adj.best_bet

    orig_ev_pct = orig_bet.ev_percent if orig_bet else None
    new_ev_pct  = adj_bet.ev_percent  if adj_bet  else None
    ev_delta_pp = ev_delta * 100  # en puntos porcentuales

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")

    if orig_ev_pct is not None and new_ev_pct is not None:
        # Determinar dirección y señal
        if ev_delta_pp >= MIN_EV_DELTA_ALERT * 100:
            color_icon  = "🟢"
            action_icon = "🟢 <b>SEÑAL: ENTRAR</b> — once favorece la apuesta"
        elif ev_delta_pp <= -MIN_EV_DELTA_ALERT * 100:
            color_icon  = "🔴"
            if new_ev_pct <= 0:
                action_icon = "🔴 <b>SEÑAL: NO ENTRAR / CASHOUT</b> — once elimina el valor"
            elif adj_bet and adj_bet.is_value:
                action_icon = "⚠️ <b>EV reducido</b> — mantener con cautela"
            else:
                action_icon = "🔴 <b>SEÑAL: CASHOUT</b> — once devora el margen"
        else:
            color_icon  = "⚪"
            action_icon = "⚪ <b>Impacto mínimo</b> — decisión sin cambios"

        # Línea principal EV
        lines.append(
            f"{color_icon} <b>EV:</b>  "
            f"{orig_ev_pct:+.1f}%  →  <b>{new_ev_pct:+.1f}%</b>  "
            f"({ev_delta_pp:+.1f}pp)"
        )

        # Selección
        if adj_bet:
            sel_line = f"   Apuesta: <b>{adj_bet.selection} @ {adj_bet.odds:.2f}</b>"
            if adj.kelly:
                sel_line += f"  |  Kelly ½: <b>{adj.kelly.stake_units:.2f}u</b>"
            lines.append(sel_line)

            # Cambio de selección
            if orig_bet and orig_bet.selection != adj_bet.selection:
                lines.append(
                    f"   ⚡ Selección giró: "
                    f"<s>{orig_bet.selection}</s> → <b>{adj_bet.selection}</b>"
                )

        lines.append("")
        lines.append(action_icon)

    elif orig_bet and new_ev_pct is None:
        lines.append(
            f"🔴 <b>EV:</b>  {orig_ev_pct:+.1f}%  →  <b>sin valor</b>"
        )
        lines.append("🔴 <b>SEÑAL: NO ENTRAR / CASHOUT</b> — onces destruyen el edge")

    elif new_ev_pct is not None and orig_ev_pct is None:
        lines.append(
            f"🟢 <b>EV:</b>  sin valor previo  →  <b>{new_ev_pct:+.1f}%</b>"
        )
        if adj_bet:
            lines.append(
                f"🟢 <b>SEÑAL: NUEVA OPORTUNIDAD</b> — "
                f"{adj_bet.selection} @ {adj_bet.odds:.2f}"
            )

    else:
        lines.append("⚪ Sin apuesta de valor antes ni después del once.")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)
