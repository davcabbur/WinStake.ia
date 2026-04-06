"""
WinStake.ia — Configuración global
Carga variables de entorno y define constantes del sistema.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys ──────────────────────────────────────────────
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
FOOTBALL_API_KEY = os.getenv("FOOTBALL_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")

# ── The Odds API ──────────────────────────────────────────
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT_KEY = "soccer_spain_la_liga"
ODDS_REGIONS = "eu"         # Cuotas europeas (decimales)
ODDS_MARKETS = "h2h,totals" # 1X2 + Over/Under (BTTS y DC calculados por modelo Poisson)
ODDS_FORMAT = "decimal"

# ── API-Football (RapidAPI) ───────────────────────────────
FOOTBALL_API_BASE = "https://v3.football.api-sports.io"
FOOTBALL_API_HOST = "v3.football.api-sports.io"
LA_LIGA_ID = 140              # ID de La Liga en API-Football
CURRENT_SEASON = 2025         # Temporada 2025-26

# ── Parámetros del modelo ─────────────────────────────────
HOME_ADVANTAGE = 0.25         # Bonus λ para equipo local
FORM_WEIGHT = 0.40            # Peso de últimos 5 partidos vs temporada
LEAGUE_AVG_GOALS = 2.65       # Media de goles por partido La Liga
MAX_GOALS_MODEL = 6           # Máximo de goles a modelar por equipo

# ── Bankroll ──────────────────────────────────────────────
BANKROLL_UNITS = 100          # Base de bankroll en unidades
KELLY_CAP = 0.10              # Máximo 10% de bankroll por apuesta
MIN_EV_THRESHOLD = 0.03       # EV mínimo para recomendar (3%)
MIN_EDGE_PERCENT = 0.05       # Edge mínimo vs mercado (5%)

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_MAX_MSG_LENGTH = 4096

# ── Caché ─────────────────────────────────────────────────
CACHE_TTL_ODDS = 30 * 60          # 30 minutos — cuotas cambian frecuentemente
CACHE_TTL_STANDINGS = 2 * 60 * 60 # 2 horas — clasificación cambia poco
CACHE_TTL_TEAM_STATS = 4 * 60 * 60 # 4 horas — stats detalladas
CACHE_TTL_H2H = 24 * 60 * 60     # 24 horas — historial no cambia
