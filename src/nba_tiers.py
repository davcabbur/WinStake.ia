"""
WinStake.ia v3.3 — Clasificación TIER de equipos NBA (Abril 2026)

Tier A — Seeding Crucial: luchan por posición de playoff, motivación máxima.
Tier B — Locked / Relaxed: seeding asegurado, posibles descansos/rotaciones.
Tier C — Eliminados / Tanking: sin nada que jugar, priorizan lotería draft.

Matching por fragmento de nombre en minúsculas (robusto frente a abreviaciones
y nombres completos distintos: "Cavaliers", "Cavs", "Cleveland", etc.).
"""

from __future__ import annotations

# ── Tier A: motivación máxima (seeding crucial) ──────────────────────────────
TIER_A_FRAGMENTS: frozenset[str] = frozenset({
    "cavaliers", "cavs", "hawks", "lakers", "rockets",
})

# ── Tier B: seeding asegurado, posibles descansos / rotaciones limitadas ─────
TIER_B_FRAGMENTS: frozenset[str] = frozenset({
    "pistons", "celtics", "thunder", "spurs",
})

# ── Tier C: eliminados o tankeando activamente ───────────────────────────────
TIER_C_FRAGMENTS: frozenset[str] = frozenset({
    "wizards", "nets", "pacers", "jazz", "kings", "grizzlies",
})

TIER_LABELS: dict[str, str] = {
    "A": "🔥 Tier A (Seeding)",
    "B": "😴 Tier B (Relaxed)",
    "C": "💀 Tier C (Tanking/Out)",
    "—": "⚪ Sin clasificar",
}

# Stake máximo para apuestas que implican a un Tier B (posible descanso)
TIER_B_STAKE_CAP: float = 1.5
# Stake máximo para Tier B + spread masivo (>15 pts): rotaciones casi seguras
TIER_B_LARGE_SPREAD_CAP: float = 0.5
# Spread mínimo para apostar A FAVOR de un Tier C
TIER_C_MIN_SPREAD: float = 20.0
# Línea de total a partir de la cual aplica el bias Under con Tier C
TIER_C_TOTAL_BIAS_LINE: float = 235.0
# Stake máximo en picks de Totales cuando hay un equipo Tier C involucrado
TIER_C_TOTALS_STAKE_CAP: float = 1.5
# Stake especulativo cuando EV > 35% pero el equipo es Tier A
TIER_A_SPECULATIVE_STAKE: float = 1.0


def get_team_tier(team_name: str) -> str:
    """
    Devuelve 'A', 'B', 'C' o '—' para un equipo dado su nombre.
    Matching por fragmento en minúsculas (insensible a formato).
    """
    low = team_name.lower()
    if any(f in low for f in TIER_A_FRAGMENTS):
        return "A"
    if any(f in low for f in TIER_B_FRAGMENTS):
        return "B"
    if any(f in low for f in TIER_C_FRAGMENTS):
        return "C"
    return "—"


def match_worst_tier(home_team: str, away_team: str) -> str:
    """
    Devuelve el peor tier entre los dos equipos del partido.
    Orden de peor a mejor: C > B > A > —
    """
    _order = {"C": 0, "B": 1, "A": 2, "—": 3}
    ht = get_team_tier(home_team)
    at = get_team_tier(away_team)
    return ht if _order.get(ht, 3) <= _order.get(at, 3) else at


def tier_label(tier: str) -> str:
    """Devuelve la etiqueta legible de un tier."""
    return TIER_LABELS.get(tier, "⚪ Sin clasificar")
