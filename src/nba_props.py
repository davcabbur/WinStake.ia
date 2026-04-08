"""
WinStake.ia v2.3 — NBA Player Props & DvP Recommendations
Genera recomendaciones diversificadas con al menos 5 categorías distintas:
  PTS | REB | AST | 3PM | PRA | S+B
usando Defense vs Position (DvP) + últimos 10 partidos + media de temporada.
"""

import math
import logging

logger = logging.getLogger(__name__)

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
    "pra":  25.0,
    "sb":    1.5,
}

STAT_LABELS = {
    "pts":  ("PTS",  "puntos"),
    "reb":  ("REB",  "rebotes"),
    "ast":  ("AST",  "asistencias"),
    "fg3m": ("3PM",  "triples"),
    "pra":  ("PRA",  "PTS+REB+AST"),
    "sb":   ("S+B",  "robos+tapones"),
}

# Orden de prioridad para asegurar diversidad de categorías
DIVERSITY_PRIORITY = ["pts", "reb", "ast", "pra", "sb", "fg3m"]


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
    Asegura que el top del ranking tenga al menos 5 categorías distintas.
    Algoritmo:
      1. Para cada categoría en DIVERSITY_PRIORITY, elige el mejor rec disponible.
      2. Rellena hasta target_total con los de mayor confianza restantes.
    Devuelve lista ordenada por confianza.
    """
    sorted_recs = sorted(recs, key=lambda x: x["confidence_score"], reverse=True)
    used_ids: set = set()
    selected: list = []

    # Fase 1: una rep por categoría (máximo 5 distintas)
    for cat in DIVERSITY_PRIORITY:
        if len(selected) >= min(5, len(DIVERSITY_PRIORITY)):
            break
        for r in sorted_recs:
            if id(r) not in used_ids and r["stat_key"] == cat:
                selected.append(r)
                used_ids.add(id(r))
                break

    # Fase 2: rellenar con los de mayor confianza
    for r in sorted_recs:
        if len(selected) >= target_total:
            break
        if id(r) not in used_ids:
            selected.append(r)
            used_ids.add(id(r))

    # Reordenar el resultado final por confianza
    return sorted(selected, key=lambda x: x["confidence_score"], reverse=True)


def generate_prop_recommendations(
    home_team: str,
    away_team: str,
    home_players: list,
    away_players: list,
    home_dvp: dict,
    away_dvp: dict,
    home_positions: dict,
    away_positions: dict,
) -> list[dict]:
    """
    Genera hasta 12 recomendaciones diversificadas (≥5 categorías distintas).
    Filtra solo jugadores del roster actual (via positions dict).
    """
    recs = []

    home_roster_ids = set(home_positions.keys())
    away_roster_ids = set(away_positions.keys())

    count = 0
    for p in away_players:
        if p["player_id"] not in away_roster_ids:
            continue
        pos = _primary_position(away_positions.get(p["player_id"], "F"))
        recs += _player_recs(p, away_team, pos, home_dvp.get(pos, {}))
        count += 1
        if count >= 10:
            break

    count = 0
    for p in home_players:
        if p["player_id"] not in home_roster_ids:
            continue
        pos = _primary_position(home_positions.get(p["player_id"], "F"))
        recs += _player_recs(p, home_team, pos, away_dvp.get(pos, {}))
        count += 1
        if count >= 10:
            break

    return _ensure_diversity(recs, target_total=12)


def _player_recs(player: dict, team: str, pos: str, dvp: dict) -> list[dict]:
    """Genera recs para PTS/REB/AST/3PM/PRA/S+B de un jugador."""
    recs = []
    league = LEAGUE_AVG_DVP.get(pos, LEAGUE_AVG_DVP["F"])

    base = {
        "pts":  (player.get("pts_season",  0), player.get("pts_l10",  0)),
        "reb":  (player.get("reb_season",  0), player.get("reb_l10",  0)),
        "ast":  (player.get("ast_season",  0), player.get("ast_l10",  0)),
        "fg3m": (player.get("fg3m_season", 0), player.get("fg3m_l10", 0)),
        "stl":  (player.get("stl_season",  0), player.get("stl_l10",  0)),
        "blk":  (player.get("blk_season",  0), player.get("blk_l10",  0)),
    }

    pra_s = base["pts"][0] + base["reb"][0] + base["ast"][0]
    pra_l = base["pts"][1] + base["reb"][1] + base["ast"][1]
    base["pra"] = (pra_s, pra_l)

    sb_s = base["stl"][0] + base["blk"][0]
    sb_l = base["stl"][1] + base["blk"][1]
    base["sb"] = (sb_s, sb_l)

    gp = player.get("gp_season", 0)

    for stat_key, (stat_lbl, stat_name) in STAT_LABELS.items():
        season_avg, l10_avg = base[stat_key]

        if season_avg < MIN_STAT[stat_key]:
            continue
        if gp < 10:
            continue

        if stat_key == "pra":
            dvp_val    = dvp.get("pts", league["pts"]) + dvp.get("reb", league["reb"]) + dvp.get("ast", league["ast"])
            league_avg = league["pts"] + league["reb"] + league["ast"]
        elif stat_key == "sb":
            dvp_val    = dvp.get("stl", league["stl"]) + dvp.get("blk", league["blk"])
            league_avg = league["stl"] + league["blk"]
        else:
            dvp_val    = dvp.get(stat_key, season_avg)
            league_avg = league.get(stat_key, season_avg)

        dvp_factor = dvp_val / league_avg if league_avg > 0 else 1.0

        effective_l10 = l10_avg if l10_avg > 0 else season_avg
        projected = (effective_l10 * 0.6 + season_avg * 0.4) * dvp_factor

        threshold = _floor_half(projected * 0.80)
        if threshold < MIN_STAT[stat_key]:
            continue

        l10_for_conf = l10_avg if l10_avg > 0 else season_avg
        confidence = _compute_confidence(season_avg, l10_for_conf, dvp_factor, projected, threshold)
        if l10_avg == 0:
            confidence *= 0.85
        if confidence < 0.45:
            continue

        direction = "concede" if dvp_factor > 1.05 else ("restringe" if dvp_factor < 0.95 else "neutro en")
        l10_text = f"{l10_avg:.1f}" if l10_avg > 0 else "N/D"
        reason = (
            f"Rival {direction} {(dvp_factor-1)*100:+.0f}% {stat_name} a su posición "
            f"(DvP {dvp_val:.1f} vs liga {league_avg:.1f}). "
            f"Temp: {season_avg:.1f} | Últ10: {l10_text}"
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


def _compute_confidence(season_avg, l10_avg, dvp_factor, projected, threshold) -> float:
    if projected <= 0:
        return 0.0
    margin_score = min((projected - threshold) / projected, 0.4) / 0.4
    if season_avg > 0:
        consistency = max(0, min(1 - abs(l10_avg - season_avg) / season_avg, 1))
    else:
        consistency = 0.5
    dvp_edge = min(max((dvp_factor - 1.0) * 2, -0.5), 0.5) + 0.5
    return margin_score * 0.5 + consistency * 0.3 + dvp_edge * 0.2
