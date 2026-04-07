<p align="center">
  <h1 align="center">🎯 WinStake.ia</h1>
  <p align="center"><strong>Sistema Automatizado de Análisis Cuantitativo de Apuestas Deportivas</strong></p>
  <p align="center">
    Inspirado en <em>Moneyball</em>, análisis deportivo avanzado y toma de decisiones estilo hedge fund.
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Liga-La%20Liga-orange?logo=laliga&logoColor=white" alt="La Liga"/>
  <img src="https://img.shields.io/badge/Liga-NBA-red?logo=nba&logoColor=white" alt="NBA"/>
  <img src="https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white" alt="Telegram"/>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License"/>
</p>

---

## 📖 ¿Qué es WinStake.ia?

WinStake.ia es un sistema de análisis cuantitativo multi-deporte que:

1. **Conecta con APIs** de datos deportivos y cuotas en tiempo real
2. **Modela probabilidades** usando Poisson (futbol) o Normal (basketball)
3. **Calcula Expected Value (EV)** comparando el modelo propio vs cuotas de mercado
4. **Detecta value bets** donde el mercado infravalora un resultado
5. **Recomienda sizing** con el criterio de Kelly
6. **Envía análisis** automáticamente a Telegram

**Deportes soportados:**
- **La Liga** — Modelo Poisson, mercados 1X2, Over/Under, BTTS, Doble Oportunidad
- **NBA** — Modelo Normal, mercados Moneyline, Spread, Totals

> **Objetivo:** Maximizar el valor esperado (EV) a largo plazo, no las victorias a corto plazo.

---

## 🧠 Filosofía — El Enfoque "Moneyball"

Este sistema se inspira en tres pilares:

### 1. Moneyball (Michael Lewis)
> "Lo que importa no es lo que crees que ves, sino lo que los datos dicen realmente."

- Buscar ineficiencias donde el mercado sobrevalora o infravalora un resultado
- Evitar sesgos narrativos (nombres grandes, rachas, "sensaciones")
- Tomar decisiones basadas exclusivamente en datos

### 2. Análisis Deportivo Avanzado
- **Futbol (Poisson + xG):** Modela goles esperados con distribución de Poisson, integra Expected Goals (xG)
- **Basketball (Normal):** Modela puntos esperados con distribución Normal, ajuste por pace y ventaja local
- **Fuerza atacante/defensiva relativa:** Comparar cada equipo contra la media de la liga

### 3. Trading Cuantitativo (Hedge Fund)
- **Expected Value (EV):** Solo apostar cuando la probabilidad real × cuota > 1
- **Criterio de Kelly:** Sizing matemático óptimo para maximizar crecimiento del bankroll
- **Gestión de riesgo:** Cap de exposición, Half-Kelly para reducir volatilidad

---

## 🏗️ Arquitectura

```
          ┌──────────────────┐     ┌────────────────────┐
          │   The Odds API   │     │  The Odds API      │
          │  soccer_spain_   │     │  basketball_nba    │
          │  la_liga         │     │  (h2h,spreads,     │
          │  (h2h,totals)    │     │   totals)          │
          └────────┬─────────┘     └────────┬───────────┘
                   │                        │
          ┌────────▼─────────┐     ┌────────▼───────────┐
          │  API-Football    │     │  API-Sports Basket  │
          │  Stats, xG       │     │  Standings, H2H     │
          └────────┬─────────┘     └────────┬───────────┘
                   │                        │
                   └────────┬───────────────┘
                            │
                   ┌────────▼──────────┐
                   │   Motor Análisis  │
                   │  ┌──────────────┐ │
                   │  │ Poisson/     │ │  Probabilidades
                   │  │ Normal       │ │  por deporte
                   │  │ EV Calc      │ │  Valor esperado
                   │  │ Kelly        │ │  Sizing óptimo
                   │  └──────────────┘ │
                   └────────┬──────────┘
                            │
              ┌─────────────┼──────────────┐
              │             │              │
     ┌────────▼──────┐ ┌───▼────┐ ┌───────▼──────┐
     │  Telegram Bot  │ │ SQLite │ │  FastAPI +   │
     │  (inline btns) │ │   DB   │ │  Angular     │
     └────────────────┘ └────────┘ └──────────────┘
```

---

## 📁 Estructura del Proyecto

```
WinStake.ia/
├── .env.example           # Template de configuración (API keys)
├── config.py              # Configuración global y constantes
├── main.py                # Entry point — orquesta todo el flujo
├── scheduler.py           # Scheduler multi-deporte (La Liga + NBA)
├── src/
│   ├── sports/
│   │   ├── config.py      # SportConfig: La Liga, NBA
│   │   └── base.py        # Clases abstractas multi-deporte
│   ├── odds_client.py     # Cliente The Odds API (cuotas, spreads)
│   ├── football_client.py # Cliente API-Football (La Liga stats)
│   ├── nba_client.py      # Cliente API-Sports Basketball (NBA stats)
│   ├── analyzer.py        # Motor de análisis (enruta Poisson/Normal)
│   ├── poisson_model.py   # Modelo Poisson (futbol)
│   ├── normal_model.py    # Modelo Normal (basketball)
│   ├── ev_calculator.py   # EV + Kelly (futbol y NBA)
│   ├── formatter.py       # Formateador Telegram (La Liga)
│   ├── nba_formatter.py   # Formateador Telegram (NBA)
│   ├── database.py        # SQLite multi-deporte
│   └── telegram_bot.py    # Bot de Telegram
├── app/                   # FastAPI backend (dashboard)
├── frontend/              # Angular 18 frontend
└── tests/                 # 149 tests (Poisson, Normal, NBA, DB)
```

---

## 🔧 Instalación

### Requisitos previos
- Python 3.10 o superior
- Cuenta en [The Odds API](https://the-odds-api.com/#get-access) (gratuita, 500 req/mes)
- Cuenta en [API-Football](https://rapidapi.com/api-sports/api/api-football) (gratuita, 100 req/día)
- Bot de Telegram creado via [@BotFather](https://t.me/BotFather)

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/davcabbur/WinStake.ia.git
cd WinStake.ia

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar API keys
cp .env.example .env
# Editar .env con tus claves reales
```

### Configurar `.env`

```env
# The Odds API
ODDS_API_KEY=tu_clave_the_odds_api

# API-Football (RapidAPI) — La Liga
FOOTBALL_API_KEY=tu_clave_api_football

# API-Sports Basketball — NBA (opcional, solo si usas --sport nba)
BASKETBALL_API_KEY=tu_clave_api_basketball

# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIjKlmNoPqRsTuVwXyZ
TELEGRAM_CHAT_ID=tu_chat_id
```

#### ¿Cómo obtener el Chat ID de Telegram?
1. Envía cualquier mensaje a tu bot
2. Visita: `https://api.telegram.org/bot<TU_TOKEN>/getUpdates`
3. Busca `"chat":{"id": XXXXXXX}` — ese es tu Chat ID

---

## 🚀 Uso

### Ejecución manual
```bash
# La Liga (default)
python main.py
python main.py --sport laliga

# NBA
python main.py --sport nba

# Opciones
python main.py --sport nba --mock-mode    # Datos simulados
python main.py --sport nba --dry-run      # Sin Telegram ni BD
python main.py --sport nba --output-csv results.csv
```

### Scheduler automático
```bash
python scheduler.py                  # Ambos deportes (La Liga + NBA)
python scheduler.py --sport nba      # Solo NBA (diario 16:00)
python scheduler.py --sport laliga   # Solo La Liga (Vie-Dom 09:00)
python scheduler.py --once --sport nba  # Ejecución única NBA
```

### API REST (dashboard)
```bash
python run_api.py
# GET /api/v1/analysis?sport=nba     # Análisis NBA
# GET /api/v1/analysis?sport=laliga  # Análisis La Liga
```

### Modo desarrollo (sin API keys)
Si no configuras las API keys, el sistema funciona con **datos simulados** para ambos deportes. Esto permite probar todo el flujo sin gastar requests.

### Output esperado
```
🚀 WinStake.ia iniciando análisis...
📊 Obteniendo cuotas de mercado...
   → 10 partidos con cuotas
📈 Obteniendo clasificación y estadísticas...
   → 20 equipos en clasificación
🧠 Ejecutando análisis cuantitativo...
   Analizando: Rayo Vallecano vs Elche
   ❌ Sin valor
   Analizando: Getafe vs Athletic Club
   ✅ VALUE BET: Empate @ 3.10 (EV: +8.5%)
   ...
📊 Resumen: 4/10 partidos con valor
📝 Formateando reporte...
📲 Enviando a Telegram...
✅ Mensaje 1/22 enviado...
✅ Análisis completado en 24.7s
```

---

## 📊 Metodología Técnica

### 1a. Modelo Poisson (La Liga)

Calcula la probabilidad de cada marcador posible (0-0 hasta 6-6):

```
P(X = k) = (lambda^k * e^-lambda) / k!
lambda_local = Ataque_local * Defensa_rival * Media_liga * Factor_casa
```

- Integra Expected Goals (xG) cuando hay datos disponibles
- Mercados: 1X2, Over/Under, BTTS, Doble Oportunidad, Handicap Asiatico

### 1b. Modelo Normal (NBA)

Para basketball, los scores (~112 pts/equipo) permiten usar distribucion Normal:

```
Pts_esperados = (PPG_propio + OPP_PPG_rival) / 2 + ventaja_local
P(home_win) = P(diff > 0) con diff ~ N(spread, std_diff)
```

- Ajuste por pace (ritmo de juego)
- Ventaja local: +3 puntos
- Mercados: Moneyline, Spread, Totals (Over/Under)

### 2. Expected Value (EV)

```
EV = (Probabilidad_real × Cuota) - 1
```

| EV | Interpretación |
|----|----------------|
| > +10% | Edge fuerte → Apuesta recomendada ✅ |
| +3% a +10% | Edge moderado → Posible apuesta 🟡 |
| < +3% | Sin edge → No apostar ❌ |

### 3. Criterio de Kelly

Sizing óptimo para maximizar crecimiento a largo plazo:

```
Kelly% = [(Probabilidad × Cuota) - 1] / (Cuota - 1)
```

- Se aplica **Half-Kelly** (mitad) para reducir volatilidad
- Cap máximo: 10% del bankroll por apuesta
- Base: 100 unidades de bankroll

### 4. Detección de Edge

Compara probabilidades del modelo vs probabilidades implícitas del mercado:

```
Prob_implícita = 1 / Cuota
Edge = Prob_real - Prob_implícita
```

Si Edge > 5%, hay una ineficiencia explotable.

---

## 🔌 APIs Utilizadas

### The Odds API
- **Propósito:** Cuotas de mercado en tiempo real
- **Deportes:** `soccer_spain_la_liga`, `basketball_nba`
- **Mercados:** h2h, totals, spreads (NBA)
- **Plan gratuito:** 500 requests/mes

### API-Football (La Liga)
- **Propósito:** Clasificación, estadísticas, xG, H2H
- **Plan gratuito:** 100 requests/dia via RapidAPI

### API-Sports Basketball (NBA)
- **Propósito:** Standings, stats de equipos, H2H
- **Mismo proveedor** que API-Football (API-Sports)

### Telegram Bot API
- **Propósito:** Enviar análisis formateados al usuario
- **Comandos:** `/laliga`, `/nba`, `/analizar`, `/roi`

---

## ⚙️ Configuración Avanzada

Todos los parámetros del modelo se pueden ajustar en `config.py`:

| Parametro | Default | Descripcion |
|-----------|---------|-------------|
| `HOME_ADVANTAGE` | 0.18 | Bonus lambda para equipo local (futbol) |
| `FORM_WEIGHT` | 0.25 | Peso de forma reciente vs temporada |
| `LEAGUE_AVG_GOALS` | 2.65 | Media de goles/partido La Liga |
| `KELLY_CAP` | 0.10 | Maximo stake por apuesta (10%) |
| `MIN_EV_THRESHOLD` | 0.03 | EV minimo para recomendar (3%) |
| `BANKROLL_UNITS` | 100 | Base de bankroll |

Parametros NBA se configuran en `src/sports/config.py`:

| Parametro | Default | Descripcion |
|-----------|---------|-------------|
| `home_advantage` | 0.03 | ~3 puntos ventaja local NBA |
| `league_avg_score` | 224.0 | Puntos totales/partido NBA |
| `odds_markets` | h2h,spreads,totals | Mercados NBA |

---

## 🧪 Tests

```bash
python -m pytest tests/ -q

# 149 tests:
# - Poisson: probabilidades, lambda, correct score, asian handicap
# - Normal (NBA): scores, spreads, totals, H2H adjustment
# - EV Calculator: futbol + NBA markets, correlaciones
# - Kelly Criterion: sizing, caps, risk levels
# - Database: save, ROI, pending results, multi-deporte
# - NBAClient: standings, team search, fuzzy match
# - Analyzer routing: futbol vs basketball
```

---

## ⚠️ Disclaimer

> **Este sistema es una herramienta de análisis informativo.** No garantiza beneficios. Las apuestas deportivas conllevan riesgo de pérdida financiera. Apuesta siempre de forma responsable y nunca más de lo que puedas permitirte perder.

---

## 📄 Licencia

MIT License — ver [LICENSE](LICENSE) para más detalles.
