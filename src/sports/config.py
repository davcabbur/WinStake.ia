"""
WinStake.ia — Configuración de deportes
Define SportConfig y el registro de deportes disponibles.
"""

from dataclasses import dataclass, field


@dataclass
class SportConfig:
    """Configuración específica de un deporte/liga."""

    # Identificadores
    key: str                        # Clave interna: "laliga", "nba"
    name: str                       # Nombre display: "La Liga", "NBA"
    sport_type: str                 # "football", "basketball"

    # The Odds API
    odds_sport_key: str             # "soccer_spain_la_liga", "basketball_nba"
    odds_markets: str               # "h2h,totals", "h2h,spreads,totals"
    odds_regions: str = "eu"

    # Stats API
    stats_api: str = ""             # "api-football", "nba-api", etc.
    league_id: int = 0              # ID de liga en la stats API
    current_season: int = 2025

    # Modelo
    model_type: str = "poisson"     # "poisson" (football), "normal" (basketball)
    home_advantage: float = 0.18
    league_avg_score: float = 2.65  # Goles/partido (football) o puntos/partido (basketball)
    max_score_model: int = 6        # Max goles a modelar (football) o no aplica (basketball)

    # Mercados disponibles para EV
    markets: list = field(default_factory=list)

    # Filtro de jornada
    matchday_window_days: int = 7   # Ventana para filtrar partidos
    matchday_span_days: int = 4     # Duración de una jornada (Vie-Lun en fútbol)

    # Display
    score_label: str = "Goles"      # "Goles" o "Puntos"
    emoji: str = "⚽"


# ── Registro de deportes ─────────────────────────────────────

LALIGA = SportConfig(
    key="laliga",
    name="La Liga",
    sport_type="football",
    odds_sport_key="soccer_spain_la_liga",
    odds_markets="h2h,totals",
    stats_api="api-football",
    league_id=140,
    current_season=2025,
    model_type="poisson",
    home_advantage=0.18,
    league_avg_score=2.65,
    max_score_model=6,
    markets=[
        "Local", "Empate", "Visitante",
        "1X", "X2", "12",
        "Over 1.5", "Under 1.5",
        "Over 2.5", "Under 2.5",
        "Over 3.5", "Under 3.5",
        "BTTS Sí", "BTTS No",
    ],
    matchday_window_days=7,
    matchday_span_days=4,
    score_label="Goles",
    emoji="⚽",
)

NBA = SportConfig(
    key="nba",
    name="NBA",
    sport_type="basketball",
    odds_sport_key="basketball_nba",
    odds_markets="h2h,spreads,totals",
    odds_regions="us",
    stats_api="nba-api",
    league_id=12,
    current_season=2025,
    model_type="normal",
    home_advantage=0.03,          # NBA home advantage ~3 puntos
    league_avg_score=224.0,       # Puntos totales por partido NBA 24/25
    max_score_model=0,            # No aplica para modelo Normal
    markets=[
        "Home", "Away",
        "Spread Home", "Spread Away",
        "Over", "Under",
    ],
    matchday_window_days=2,       # NBA juega casi a diario
    matchday_span_days=1,
    score_label="Puntos",
    emoji="🏀",
)

# Registro global
SPORTS: dict[str, SportConfig] = {
    "laliga": LALIGA,
    "nba": NBA,
}


def get_sport(key: str) -> SportConfig:
    """Obtiene configuración de deporte por clave."""
    if key not in SPORTS:
        available = ", ".join(SPORTS.keys())
        raise ValueError(f"Deporte '{key}' no encontrado. Disponibles: {available}")
    return SPORTS[key]
