"""
WinStake.ia v3.2 — NBA Player Props & DvP Recommendations
Genera recomendaciones de props estadísticamente aislados:
  PTS | REB | AST | 3PM
usando Defense vs Position (DvP) + últimos 10 partidos + media de temporada.

Props compuestos (PRA, S+B) eliminados por alta varianza intrínseca.

Mejoras v3.2:
  - Blowout & Garbage Time Adjuster: reduce confianza en AST de forwards
    en victorias proyectadas cómodas.
  - Hot teammate weight: si un compañero de equipo está en racha anotadora
    (L10 pts ≥ 20% sobre media de temporada y >18 pts), se reduce la
    proyección de asistencias del forward del mismo equipo.
  - Umbrales estrictos para forwards: AST solo recomendada con ≥27 MPG
    proyectados y confianza mínima de 0.60.
  - Confianza mínima global subida a 0.55 para filtrado más estricto.
"""

import math
import logging

from src.blowout_adjuster import BlowoutContext, adjust_prop_confidence_for_blowout

logger = logging.getLogger(__name__)

# Minutos mínimos para props de AST de forwards (más estricto que el mínimo general)
_MIN_MPG_FORWARD_AST = 27.0
# Confianza mínima para recomendar AST de forward
_MIN_CONF_FORWARD_AST = 0.60
# Umbral de "hot scorer": L10 > season × factor Y L10 pts por encima de este valor
_HOT_SCORER_L10_FACTOR = 1.20
_HOT_SCORER_L10_MIN    = 18.0
# Factor de reducción de asistencias cuando hay un hot scorer en el mismo equipo
_HOT_TEAMMATE_AST_REDUCTION = 0.08  # 8% de reducción en projected assists

# ── Media de liga por posición (2025-26) ────────────────────
LEAGUE_AVG_DVP = {
    "G": {"pts": 13.5, "reb": 3.8, "ast": 3.8, "fg3m": 1.6, "stl": 0.9,  "blk": 0.2},
    "F": {"pts": 11.0, "reb": 5.2, "ast": 2.5, "fg3m": 1.1, "stl": 0.7,  "blk": 0.4},
    "C": {"pts":  9.5, "reb": 7.8, "ast": 1.7, "fg3m": 0.4, "stl": 0.45, "blk": 0.8},
}

# ── Umbrales mínimos para recomendar ────────────────────────
MIN_STAT = {
    "pts":  14.0,
    "reb":   5.0,
    "ast":   4.0,
    "fg3m":  1.5,
}

# Umbral 3PM extra-alto para Centers (no tiradores naturales)
_FG3M_MIN_BY_POS = {"G": 1.5, "F": 1.5, "C": 2.5}

# Minutos mínimos para considerar a un jugador (evita role players de pocas rotaciones)
_MIN_MPG = 15.0

STAT_LABELS = {
    "pts":  ("PTS",  "puntos"),
    "reb":  ("REB",  "rebotes"),
    "ast":  ("AST",  "asistencias"),
    "fg3m": ("3PM",  "triples"),
}

# Orden de prioridad para asegurar diversidad de categorías
DIVERSITY_PRIORITY = ["pts", "reb", "ast", "fg3m"]


def _floor_half(x: float) -> float:
    return math.floor(x * 2) / 2


def _primary_position(pos_str: str) -> str:
    if not pos_str:
        return "F"
    p = pos_str.split("-")[0].strip().upper()
    return p if p in ("G", "F", "C") else "F"


def _estimated_book_odds(confidence: float) -> float:
    """
    Cuota estimada que ofrecería un libro estándar.
      conf 0.85 → ~1.74  (≈ -136 americano)
      conf 0.70 → ~1.83  (≈ -120)
      conf 0.50 → ~1.91  (≈ -110)
    """
    raw = 1.85 - (confidence - 0.5) * 0.35
    return round(max(1.65, min(2.05, raw)), 2)


def _ensure_diversity(recs: list, target_total: int = 12) -> list:
    """
    Asegura que el top del ranking tenga al menos 4 categorías distintas (PTS/REB/AST/3PM)
    y no más de 2 props del mismo jugador.
    Algoritmo:
      1. Para cada categoría en DIVERSITY_PRIORITY, elige el mejor rec disponible.
      2. Rellena hasta target_total respetando el límite de 2 por jugador.
    Devuelve lista ordenada por confianza.
    """
    sorted_recs = sorted(recs, key=lambda x: x["confidence_score"], reverse=True)
    # Improvement 10: use (player, stat_key) tuple instead of id() for deduplication
    used_keys: set = set()
    player_count: dict = {}
    selected: list = []

    # Fase 1: una rep por categoría (máximo 6 distintas)
    for cat in DIVERSITY_PRIORITY:
        if len(selected) >= min(4, len(DIVERSITY_PRIORITY)):
            break
        for r in sorted_recs:
            key = (r["player"], r["stat_key"])
            if key not in used_keys and r["stat_key"] == cat:
                pname = r["player"]
                if player_count.get(pname, 0) < 2:
                    selected.append(r)
                    used_keys.add(key)
                    player_count[pname] = player_count.get(pname, 0) + 1
                    break

    # Fase 2: rellenar con los de mayor confianza (max 2 por jugador)
    for r in sorted_recs:
        if len(selected) >= target_total:
            break
        key = (r["player"], r["stat_key"])
        if key not in used_keys:
            pname = r["player"]
            if player_count.get(pname, 0) < 2:
                selected.append(r)
                used_keys.add(key)
                player_count[pname] = player_count.get(pname, 0) + 1

    # Reordenar el resultado final por confianza
    return sorted(selected, key=lambda x: x["confidence_score"], reverse=True)


def _detect_hot_scorers(players: list, positions: dict) -> set:
    """
    Devuelve el conjunto de player_ids con racha anotadora activa:
      L10 pts ≥ season_pts × _HOT_SCORER_L10_FACTOR  Y  L10 pts ≥ _HOT_SCORER_L10_MIN
    """
    hot: set = set()
    for p in players:
        pts_s = p.get("pts_season", 0)
        pts_l = p.get("pts_l10", 0)
        if pts_l >= _HOT_SCORER_L10_MIN and pts_s > 0 and pts_l >= pts_s * _HOT_SCORER_L10_FACTOR:
            hot.add(p["player_id"])
    return hot


def generate_prop_recommendations(
    home_team: str,
    away_team: str,
    home_players: list,
    away_players: list,
    home_dvp: dict,
    away_dvp: dict,
    home_positions: dict,
    away_positions: dict,
    home_team_id: int = None,
    away_team_id: int = None,
    b2b_teams: set = None,
    blowout_ctx: "BlowoutContext | None" = None,
) -> list[dict]:
    """
    Genera hasta 12 recomendaciones diversificadas (≥5 categorías distintas).
    Filtra solo jugadores del roster actual (via positions dict).

    Parámetros nuevos v2.4:
      blowout_ctx: contexto de blowout (BlowoutContext). Si se detecta victoria
                   cómoda, se reducirá la confianza en AST/PRA de forwards.
    """
    recs = []
    b2b = b2b_teams or set()

    home_roster_ids = set(home_positions.keys())
    away_roster_ids = set(away_positions.keys())

    # Determine if defending team is on B2B (their defense is weaker)
    home_on_b2b = home_team_id in b2b if home_team_id else False
    away_on_b2b = away_team_id in b2b if away_team_id else False

    # Detectar hot scorers por equipo para ajuste de distribución ofensiva
    home_hot = _detect_hot_scorers(home_players, home_positions)
    away_hot = _detect_hot_scorers(away_players, away_positions)

    count = 0
    for p in away_players:
        if p["player_id"] not in away_roster_ids:
            continue
        if away_team_id and p.get("team_id") and p["team_id"] != away_team_id:
            logger.warning(
                f"Player {p['player_name']} team_id mismatch: "
                f"expected {away_team_id} ({away_team}), got {p['team_id']} — skipping"
            )
            continue
        pos = _primary_position(away_positions.get(p["player_id"], "F"))
        recs += _player_recs(
            p, away_team, pos, home_dvp.get(pos, {}),
            attacker_on_b2b=away_on_b2b,
            defender_on_b2b=home_on_b2b,
            team_has_hot_scorer=bool(away_hot - {p["player_id"]}),
            blowout_ctx=blowout_ctx,
        )
        count += 1
        if count >= 10:
            break

    count = 0
    for p in home_players:
        if p["player_id"] not in home_roster_ids:
            continue
        if home_team_id and p.get("team_id") and p["team_id"] != home_team_id:
            logger.warning(
                f"Player {p['player_name']} team_id mismatch: "
                f"expected {home_team_id} ({home_team}), got {p['team_id']} — skipping"
            )
            continue
        pos = _primary_position(home_positions.get(p["player_id"], "F"))
        recs += _player_recs(
            p, home_team, pos, away_dvp.get(pos, {}),
            attacker_on_b2b=home_on_b2b,
            defender_on_b2b=away_on_b2b,
            team_has_hot_scorer=bool(home_hot - {p["player_id"]}),
            blowout_ctx=blowout_ctx,
        )
        count += 1
        if count >= 10:
            break

    return _ensure_diversity(recs, target_total=12)


def _player_recs(
    player: dict,
    team: str,
    pos: str,
    dvp: dict,
    attacker_on_b2b: bool = False,
    defender_on_b2b: bool = False,
    team_has_hot_scorer: bool = False,
    blowout_ctx: "BlowoutContext | None" = None,
) -> list[dict]:
    """Genera recs para PTS/REB/AST/3PM de un jugador.

    Parámetros:
      team_has_hot_scorer: hay un compañero de equipo en racha (L10 pts muy alta)
                           → reduce projected de AST en forwards un 8%.
      blowout_ctx:         contexto de blowout → penaliza AST de forwards.
    """
    recs = []
    league = LEAGUE_AVG_DVP.get(pos, LEAGUE_AVG_DVP["F"])

    base = {
        "pts":  (player.get("pts_season",  0), player.get("pts_l10",  0)),
        "reb":  (player.get("reb_season",  0), player.get("reb_l10",  0)),
        "ast":  (player.get("ast_season",  0), player.get("ast_l10",  0)),
        "fg3m": (player.get("fg3m_season", 0), player.get("fg3m_l10", 0)),
    }

    gp = player.get("gp_season", 0)
    mpg = player.get("mpg_season", 0.0)

    # Filtrar jugadores con muy pocos minutos (role players de fondo de rotación)
    if mpg > 0 and mpg < _MIN_MPG:
        return []

    for stat_key, (stat_lbl, stat_name) in STAT_LABELS.items():
        season_avg, l10_avg = base[stat_key]

        # Umbral dinámico por posición para 3PM (Centers necesitan barra más alta)
        min_threshold = MIN_STAT[stat_key]
        if stat_key == "fg3m":
            min_threshold = _FG3M_MIN_BY_POS.get(pos, 1.5)

        if season_avg < min_threshold:
            continue
        if gp < 10:
            continue

        dvp_val    = dvp.get(stat_key, season_avg)
        league_avg = league.get(stat_key, season_avg)

        dvp_factor = dvp_val / league_avg if league_avg > 0 else 1.0

        # Defender on B2B → their defense is ~8% weaker
        if defender_on_b2b:
            dvp_factor *= 1.08

        effective_l10 = l10_avg if l10_avg > 0 else season_avg
        projected = (effective_l10 * 0.6 + season_avg * 0.4) * dvp_factor

        # ── Hot teammate: compañero en racha anotadora → reduce AST en F ──
        # Si otro jugador del equipo está disparado (L10 pts muy por encima de
        # su media), ese jugador acapara más el balón → forwards generan menos
        # asistencias de las proyectadas.
        hot_note = ""
        if team_has_hot_scorer and stat_key == "ast" and pos == "F":
            projected = round(projected * (1.0 - _HOT_TEAMMATE_AST_REDUCTION), 2)
            hot_note = " [🔥 Compañero hot]"

        threshold = _floor_half(projected * 0.80)
        if threshold < MIN_STAT[stat_key]:
            continue

        # ── Umbrales estrictos para AST de forwards ──────────────────────
        # Solo alta confianza si el forward tiene ≥27 MPG proyectados y
        # el partido se proyecta cerrado (no blowout).
        if stat_key == "ast" and pos == "F":
            if mpg < _MIN_MPG_FORWARD_AST:
                continue

        l10_for_conf = l10_avg if l10_avg > 0 else season_avg
        confidence = _compute_confidence(
            season_avg, l10_for_conf, dvp_factor, projected, threshold, gp, mpg
        )
        if l10_avg == 0:
            confidence *= 0.85
        # Attacker on B2B → reduce confidence by 0.05
        if attacker_on_b2b:
            confidence -= 0.05

        # ── Penalización por blowout (forwards AST/PRA) ───────────────────
        if blowout_ctx is not None:
            confidence = adjust_prop_confidence_for_blowout(
                confidence, stat_key, pos, blowout_ctx
            )

        # ── Umbral mínimo de confianza: más estricto para AST de forwards ──
        min_conf = _MIN_CONF_FORWARD_AST if (stat_key == "ast" and pos == "F") else 0.55
        if confidence < min_conf:
            continue

        direction = "concede" if dvp_factor > 1.05 else ("restringe" if dvp_factor < 0.95 else "neutro en")
        l10_text = f"{l10_avg:.1f}" if l10_avg > 0 else "N/D"
        b2b_note = ""
        if attacker_on_b2b:
            b2b_note = " [⚠️ B2B jugador]"
        if defender_on_b2b:
            b2b_note += " [⚡ Rival B2B]"
        reason = (
            f"Rival {direction} {(dvp_factor-1)*100:+.0f}% {stat_name} a su posición "
            f"(DvP {dvp_val:.1f} vs liga {league_avg:.1f}). "
            f"Temp: {season_avg:.1f} | Últ10: {l10_text}{b2b_note}{hot_note}"
        )

        recs.append({
            "player":           player["player_name"],
            "team":             team,
            "pos":              pos,
            "stat_key":         stat_key,
            "stat_label":       stat_lbl,
            "stat_name":        stat_name,
            "threshold":        threshold,
            "projected":        round(projected, 1),
            "dvp_factor":       round(dvp_factor, 2),
            "season_avg":       season_avg,
            "l10_avg":          l10_avg,
            "reason":           reason,
            "confidence_score": round(confidence, 2),
            "estimated_odds":   _estimated_book_odds(confidence),
        })

    return recs


def _compute_confidence(
    season_avg, l10_avg, dvp_factor, projected, threshold,
    gp: int = 40, mpg: float = 25.0,
) -> float:
    """
    Compute confidence score for a prop.

    Penalties applied:
    - Sample size: scales from 0.80 (10 GP) to 1.00 (40+ GP)
    - Minutes: scales from 0.75 (15 MPG) to 1.00 (28+ MPG), penalizes role players
    """
    if projected <= 0:
        return 0.0
    margin_score = min((projected - threshold) / projected, 0.4) / 0.4
    if season_avg > 0:
        consistency = max(0, min(1 - abs(l10_avg - season_avg) / season_avg, 1))
    else:
        consistency = 0.5
    dvp_edge = min(max((dvp_factor - 1.0) * 2, -0.5), 0.5) + 0.5
    raw = margin_score * 0.5 + consistency * 0.3 + dvp_edge * 0.2

    # Sample size penalty: 0.80 at 10 GP → 1.00 at 40+ GP
    sample_factor = min(1.0, 0.80 + (gp - 10) * (0.20 / 30))
    sample_factor = max(0.80, sample_factor)

    # Minutes penalty: 0.75 at 15 MPG → 1.00 at 28+ MPG
    # Role players with unstable minutes are less predictable
    if mpg > 0:
        mpg_factor = min(1.0, 0.75 + (mpg - _MIN_MPG) * (0.25 / 13))
        mpg_factor = max(0.75, mpg_factor)
    else:
        mpg_factor = 1.0

    return raw * sample_factor * mpg_factor
