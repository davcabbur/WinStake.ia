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
BASKETBALL_API_KEY = os.getenv("BASKETBALL_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")
WORLD_CUP_API_KEY = os.getenv("WORLD_CUP_API_KEY", "")

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

# ── World Cup API (worldcupapi.com) ───────────────────────
WORLD_CUP_API_BASE = "https://api.worldcupapi.com"
WORLD_CUP_LANG = os.getenv("WINSTAKE_WC_LANG", "es")  # la API acepta &lang=

# ── Parámetros del modelo ─────────────────────────────────
HOME_ADVANTAGE = 0.18         # Bonus λ para equipo local (La Liga post-COVID: ~0.15-0.20)
FORM_WEIGHT = 0.25            # Peso base de últimos 5 partidos (se reduce con más jornadas)
LEAGUE_AVG_GOALS = 2.65       # Media de goles por partido La Liga (se recalcula dinámicamente)
MAX_GOALS_MODEL = 6           # Máximo de goles a modelar por equipo

# ── Bankroll ──────────────────────────────────────────────
BANKROLL_UNITS = 100          # Base de bankroll en unidades
KELLY_CAP = 0.10              # Máximo 10% de bankroll por apuesta
MIN_EV_THRESHOLD = 0.03       # EV mínimo para is_value (Pick Oficial pleno)
MARGINAL_EV_THRESHOLD = 0.01  # EV mínimo para is_marginal (Pick Oficial con stake reducido)
MIN_EDGE_PERCENT = 0.05       # Edge mínimo vs mercado (5%)

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_MAX_MSG_LENGTH = 4096

# ── Caché ─────────────────────────────────────────────────
CACHE_TTL_ODDS = 30 * 60          # 30 minutos — cuotas cambian frecuentemente
CACHE_TTL_STANDINGS = 2 * 60 * 60 # 2 horas — clasificación cambia poco
CACHE_TTL_TEAM_STATS = 4 * 60 * 60 # 4 horas — stats detalladas
CACHE_TTL_H2H = 24 * 60 * 60     # 24 horas — historial no cambia

# World Cup API — TTLs calibrados para no quemar las 1500 requests del free trial
CACHE_TTL_WC_LIVE      = 60          # livescores / livestandings (en vivo)
CACHE_TTL_WC_FIXTURES  = 6 * 60 * 60 # fixtures (calendario, cambia poco)
CACHE_TTL_WC_STANDINGS = 30 * 60     # standings
CACHE_TTL_WC_MATCH     = 5 * 60      # events / statistics / lineups / commentary
CACHE_TTL_WC_STATIC    = 24 * 60 * 60 # squads / history / head2head / goalscorers / cards

# ── Paper trading ─────────────────────────────────────────
# Cuando =1, el motor de análisis usa la cuota cruda del bookmaker elegido
# (chosen_book_odds) en lugar de la trimmed mean (avg_odds). Por defecto OFF
# para no alterar las recomendaciones que se envían a Telegram en producción.
USE_RAW_ODDS = os.getenv("WINSTAKE_USE_RAW_ODDS", "0") == "1"

# ── Feature flags ─────────────────────────────────────────
# OFF por defecto: el plan free de API-Football no permite la temporada actual.
# Para reactivar: WINSTAKE_LALIGA_ENABLED=1 en el entorno.
LALIGA_ENABLED = os.getenv("WINSTAKE_LALIGA_ENABLED", "0") == "1"
