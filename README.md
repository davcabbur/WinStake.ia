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
  <img src="https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white" alt="Telegram"/>
  <img src="https://img.shields.io/badge/License-MIT-green" alt="License"/>
</p>

---

## 📖 ¿Qué es WinStake.ia?

WinStake.ia es un sistema de análisis cuantitativo que:

1. **Conecta con APIs** de datos deportivos y cuotas en tiempo real
2. **Modela probabilidades** usando distribución de Poisson con ajustes bayesianos
3. **Calcula Expected Value (EV)** comparando el modelo propio vs cuotas de mercado
4. **Detecta value bets** donde el mercado infravalora un resultado
5. **Recomienda sizing** con el criterio de Kelly
6. **Envía análisis** automáticamente a Telegram

> **Objetivo:** Maximizar el valor esperado (EV) a largo plazo, no las victorias a corto plazo.

---

## 🧠 Filosofía — El Enfoque "Moneyball"

Este sistema se inspira en tres pilares:

### 1. Moneyball (Michael Lewis)
> "Lo que importa no es lo que crees que ves, sino lo que los datos dicen realmente."

- Buscar ineficiencias donde el mercado sobrevalora o infravalora un resultado
- Evitar sesgos narrativos (nombres grandes, rachas, "sensaciones")
- Tomar decisiones basadas exclusivamente en datos

### 2. Análisis Deportivo Avanzado (xG, Poisson)
- **Expected Goals (xG):** No medir solo goles, sino la calidad de las ocasiones
- **Distribución de Poisson:** Modelo estadístico que predice la probabilidad de cada resultado basándose en los goles esperados de cada equipo
- **Fuerza atacante/defensiva relativa:** Comparar cada equipo contra la media de la liga

### 3. Trading Cuantitativo (Hedge Fund)
- **Expected Value (EV):** Solo apostar cuando la probabilidad real × cuota > 1
- **Criterio de Kelly:** Sizing matemático óptimo para maximizar crecimiento del bankroll
- **Gestión de riesgo:** Cap de exposición, Half-Kelly para reducir volatilidad

---

## 🏗️ Arquitectura

```
                    ┌──────────────────┐
                    │   The Odds API   │ ── Cuotas 1X2, O/U
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  API-Football    │ ── Stats, xG, Standings
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Motor Análisis  │
                    │  ┌─────────────┐ │
                    │  │  Poisson    │ │ ── Probabilidades reales
                    │  │  EV Calc    │ │ ── Valor esperado
                    │  │  Kelly      │ │ ── Sizing óptimo
                    │  │  Edge Det.  │ │ ── Ineficiencias de mercado
                    │  └─────────────┘ │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Formateador     │ ── HTML para Telegram
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Bot Telegram 📱 │ ── Envío automático
                    └──────────────────┘
```

---

## 📁 Estructura del Proyecto

```
WinStake.ia/
├── .env.example           # Template de configuración (API keys)
├── .gitignore             # Archivos ignorados por Git
├── requirements.txt       # Dependencias Python
├── config.py              # Configuración global y constantes
├── main.py                # Entry point — orquesta todo el flujo
├── README.md              # Esta documentación
├── src/
│   ├── __init__.py
│   ├── odds_client.py     # Cliente The Odds API (cuotas)
│   ├── football_client.py # Cliente API-Football (stats)
│   ├── analyzer.py        # Motor de análisis cuantitativo
│   ├── formatter.py       # Formateador mensajes Telegram
│   └── telegram_bot.py    # Bot de Telegram
└── tests/
    ├── __init__.py
    └── test_analyzer.py   # Tests del motor de análisis
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

# API-Football (RapidAPI)
FOOTBALL_API_KEY=tu_clave_api_football

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
# En Windows (con el entorno virtual activado):
python main.py
# O directamente:
.\venv\Scripts\python.exe main.py
```

### Modo desarrollo (sin API keys)
Si no configuras las API keys, el sistema funciona con **datos simulados** basados en la clasificación real de La Liga 2025-26 (Jornada 29). Esto permite probar todo el flujo sin gastar requests.

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

### 1. Modelo de Poisson

El corazón del sistema. Calcula la probabilidad de cada marcador posible (0-0 hasta 6-6):

```
P(X = k) = (λ^k × e^-λ) / k!
```

Donde **λ** (lambda) es el número esperado de goles:

```
λ_local = Ataque_local × Defensa_rival × Media_liga × Factor_casa
λ_visitante = Ataque_visitante × Defensa_rival × Media_liga × Factor_visitante
```

- **Ataque** = GF del equipo / GF medio de la liga
- **Defensa** = GC del rival / GC medio de la liga
- **Factor casa** = +25% bonus para local (configurable)

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
- **Propósito:** Cuotas de mercado en tiempo real de múltiples casas de apuestas
- **Endpoint:** `GET /v4/sports/soccer_spain_la_liga/odds`
- **Mercados:** h2h (1X2), totals (Over/Under)
- **Plan gratuito:** 500 requests/mes
- **Sitio:** [the-odds-api.com](https://the-odds-api.com)

### API-Football
- **Propósito:** Clasificación, estadísticas de equipos, historial directo
- **Endpoints:** `/standings`, `/teams/statistics`, `/fixtures/headtohead`
- **Plan gratuito:** 100 requests/día via RapidAPI
- **Sitio:** [api-football.com](https://www.api-football.com)

### Telegram Bot API
- **Propósito:** Enviar análisis formateados al usuario
- **Formato:** HTML con emojis y estructura visual
- **Límite:** 4096 caracteres por mensaje (split automático)

---

## ⚙️ Configuración Avanzada

Todos los parámetros del modelo se pueden ajustar en `config.py`:

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `HOME_ADVANTAGE` | 0.25 | Bonus de goles para equipo local |
| `FORM_WEIGHT` | 0.40 | Peso de forma reciente vs temporada |
| `LEAGUE_AVG_GOALS` | 2.65 | Media de goles por partido en La Liga |
| `KELLY_CAP` | 0.10 | Máximo stake por apuesta (10%) |
| `MIN_EV_THRESHOLD` | 0.03 | EV mínimo para recomendar (3%) |
| `BANKROLL_UNITS` | 100 | Base de bankroll |

---

## 🧪 Tests

```bash
# Ejecutar tests del motor de análisis
python tests/test_analyzer.py

# Tests incluidos:
# ✅ Probabilidades Poisson suman 100%
# ✅ Ventaja local con λ mayor
# ✅ Simetría con λ iguales
# ✅ EV positivo y negativo
# ✅ Kelly: normal, cero, capado
# ✅ Conversión cuotas → probabilidades
# ✅ Eliminación de overround
# ✅ Análisis completo de integración
```

---

## ⚠️ Disclaimer

> **Este sistema es una herramienta de análisis informativo.** No garantiza beneficios. Las apuestas deportivas conllevan riesgo de pérdida financiera. Apuesta siempre de forma responsable y nunca más de lo que puedas permitirte perder.

---

## 📄 Licencia

MIT License — ver [LICENSE](LICENSE) para más detalles.
