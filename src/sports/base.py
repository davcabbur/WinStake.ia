"""
WinStake.ia — Clases base abstractas para multi-deporte
Definen la interfaz que cada deporte debe implementar.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from src.sports.config import SportConfig


# ── Resultado de análisis genérico ───────────────────────────

@dataclass
class MatchPrediction:
    """Predicción genérica de un partido (cualquier deporte)."""
    home_team: str = ""
    away_team: str = ""
    commence_time: str = ""
    match_id: str = ""
    sport: str = ""

    # Probabilidades principales (siempre disponibles)
    home_win_prob: float = 0.0
    away_win_prob: float = 0.0
    draw_prob: float = 0.0          # 0 para deportes sin empate (NBA)

    # Score esperado
    home_score_expected: float = 0.0
    away_score_expected: float = 0.0

    # Mercados extra (dict flexible por deporte)
    extra_markets: dict = field(default_factory=dict)


# ── Modelo de predicción ─────────────────────────────────────

class BaseMatchModel(ABC):
    """Interfaz base para modelos de predicción por deporte."""

    def __init__(self, sport_config: SportConfig):
        self.config = sport_config

    @abstractmethod
    def predict(
        self,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
        h2h_data: Optional[list] = None,
    ) -> MatchPrediction:
        """
        Genera predicción para un partido.
        Cada deporte implementa su propio modelo estadístico.
        """
        ...

    @abstractmethod
    def calculate_expected_scores(
        self,
        home_stats: Optional[dict],
        away_stats: Optional[dict],
    ) -> tuple[float, float]:
        """Calcula score esperado (goles, puntos, etc.) para cada equipo."""
        ...

    def update_league_avg(self, standings: list[dict]) -> None:
        """Recalibra la media de la liga desde datos reales. Override opcional."""
        pass


# ── Cliente de estadísticas ──────────────────────────────────

class BaseStatsClient(ABC):
    """Interfaz base para clientes de estadísticas por deporte."""

    def __init__(self, sport_config: SportConfig):
        self.config = sport_config

    @abstractmethod
    def get_standings(self) -> list[dict]:
        """Obtiene clasificación/standings de la liga."""
        ...

    @abstractmethod
    def get_team_stats(self, team_id: int) -> Optional[dict]:
        """Obtiene estadísticas detalladas de un equipo."""
        ...

    @abstractmethod
    def get_h2h(self, team1_id: int, team2_id: int) -> list[dict]:
        """Obtiene historial directo entre dos equipos."""
        ...

    @abstractmethod
    def find_team_in_standings(self, team_name: str, standings: list[dict]) -> Optional[dict]:
        """Busca un equipo en la clasificación."""
        ...

    def get_top_scorers(self) -> list[dict]:
        """Obtiene goleadores/anotadores. Override por deporte."""
        return []

    def get_players_for_match(self, home: str, away: str, scorers: list[dict]) -> dict:
        """Filtra jugadores relevantes para un partido."""
        return {"home": [], "away": []}


# ── Formateador ──────────────────────────────────────────────

class BaseFormatter(ABC):
    """Interfaz base para formatear análisis como mensajes de Telegram."""

    def __init__(self, sport_config: SportConfig):
        self.config = sport_config

    @abstractmethod
    def format_match(self, analysis) -> str:
        """Formatea un análisis individual como HTML para Telegram."""
        ...

    @abstractmethod
    def format_summary(self, analyses: list) -> str:
        """Formatea el resumen ejecutivo de la jornada."""
        ...
