# WorldCupClient Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir `src/worldcup_client.py`, un cliente Python para la World Cup API (api.worldcupapi.com) que cubra sus 13 endpoints.

**Architecture:** Calca el patrón de `OddsClient`/`FootballClient`: sesión `requests` con retry/backoff + `APICache` en disco + logging en español. Un helper privado `_cached_get` centraliza el flujo (key vacía → caché → request → cache.set) para mantenerlo DRY. **Sin modo mock**: si falta la key o falla la API, los métodos devuelven `None`. Idioma `es` por defecto, inyectado en toda request.

**Tech Stack:** Python 3.12, `requests`, `urllib3.Retry`, `pytest`, `unittest.mock` (el repo no usa `responses`/`requests-mock`).

**Contrato de retorno:** cada método devuelve el JSON decodificado (dict o list, tal cual lo entregue la API) o `None` en cualquier fallo o key vacía. El shape fino se normalizará tras la primera llamada real (fuera de alcance).

---

### Task 1: Config — constantes de la World Cup API

**Files:**
- Modify: `config.py` (zona API Keys ~línea 17 y zona Caché ~línea 52)

- [ ] **Step 1: Añadir base + idioma tras la línea de API keys**

En `config.py`, justo después de la sección `# ── API-Football (RapidAPI) ──` (tras la línea `CURRENT_SEASON = 2025`), añadir:

```python
# ── World Cup API (worldcupapi.com) ───────────────────────
WORLD_CUP_API_BASE = "https://api.worldcupapi.com"
WORLD_CUP_LANG = os.getenv("WINSTAKE_WC_LANG", "es")  # la API acepta &lang=
```

- [ ] **Step 2: Añadir la API key en la sección API Keys**

En `config.py`, tras la línea `DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")` (línea 17), añadir:

```python
WORLD_CUP_API_KEY = os.getenv("WORLD_CUP_API_KEY", "")
```

- [ ] **Step 3: Añadir los TTLs de caché**

En `config.py`, tras la línea `CACHE_TTL_H2H = 24 * 60 * 60     # 24 horas — historial no cambia` (línea 52), añadir:

```python
# World Cup API — TTLs calibrados para no quemar las 1500 requests del free trial
CACHE_TTL_WC_LIVE      = 60          # livescores / livestandings (en vivo)
CACHE_TTL_WC_FIXTURES  = 6 * 60 * 60 # fixtures (calendario, cambia poco)
CACHE_TTL_WC_STANDINGS = 30 * 60     # standings
CACHE_TTL_WC_MATCH     = 5 * 60      # events / statistics / lineups / commentary
CACHE_TTL_WC_STATIC    = 24 * 60 * 60 # squads / history / head2head / goalscorers / cards
```

- [ ] **Step 4: Verificar que carga sin errores**

Run: `python -c "import config; print(config.WORLD_CUP_API_BASE, config.WORLD_CUP_LANG, config.CACHE_TTL_WC_LIVE)"`
Expected: `https://api.worldcupapi.com es 60`

- [ ] **Step 5: Commit**

```bash
git add config.py
git commit -m "feat(config): constantes World Cup API (base, lang, TTLs)"
```

---

### Task 2: Esqueleto del cliente + `get_livescores`

Implementa la sesión, `__init__`, `_request`, `_cached_get` y el primer método. Estos tests cubren el comportamiento transversal (key vacía, inyección de key/lang, error HTTP, caché) usando `get_livescores` como punto de entrada.

**Files:**
- Create: `src/worldcup_client.py`
- Test: `tests/test_worldcup_client.py`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `tests/test_worldcup_client.py`:

```python
"""Tests para WorldCupClient — sin pegar a la API real (no gastar requests)."""

from unittest.mock import MagicMock

import requests
import pytest

from src.cache import APICache
from src.worldcup_client import WorldCupClient


def _fake_response(json_data, status_ok=True):
    """Construye un fake requests.Response."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.headers = {"x-requests-remaining": "1499"}
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return resp


def _client(tmp_path, api_key="testkey", lang=None):
    """Cliente con caché aislada en tmp_path."""
    c = WorldCupClient(api_key=api_key, lang=lang)
    c.cache = APICache(cache_dir=str(tmp_path))
    return c


def test_empty_key_no_http(tmp_path):
    c = _client(tmp_path, api_key="")
    c.session.get = MagicMock()
    assert c.get_livescores() is None
    c.session.get.assert_not_called()


def test_request_injects_key_and_lang(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({"ok": 1}))
    c.get_livescores()
    _, kwargs = c.session.get.call_args
    assert kwargs["params"]["key"] == "testkey"
    assert kwargs["params"]["lang"] == "es"


def test_livescores_url_and_return(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({"v": 1}))
    result = c.get_livescores()
    assert result == {"v": 1}
    args, _ = c.session.get.call_args
    assert args[0].endswith("/livescores")


def test_second_call_uses_cache(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({"v": 1}))
    first = c.get_livescores()
    second = c.get_livescores()
    assert first == second == {"v": 1}
    assert c.session.get.call_count == 1  # la 2ª se sirve de caché


def test_cache_key_varies_with_lang(tmp_path):
    c_es = _client(tmp_path, lang="es")
    c_es.session.get = MagicMock(return_value=_fake_response({"l": "es"}))
    c_es.get_livescores()
    c_en = _client(tmp_path, lang="en")
    c_en.session.get = MagicMock(return_value=_fake_response({"l": "en"}))
    c_en.get_livescores()
    # Idioma distinto → cache key distinta → sí hace HTTP
    assert c_en.session.get.call_count == 1


def test_http_error_returns_none(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response(None, status_ok=False))
    assert c.get_livescores() is None
```

- [ ] **Step 2: Ejecutar los tests para verificar que fallan**

Run: `pytest tests/test_worldcup_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.worldcup_client'`

- [ ] **Step 3: Crear `src/worldcup_client.py` con esqueleto + `get_livescores`**

```python
"""
WinStake.ia — Cliente de la World Cup API (api.worldcupapi.com)
Cubre los 13 endpoints. Free trial con tope de 1500 requests → caché agresiva.
Sin modo mock: si falta la key o falla la API, devuelve None y loggea.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from typing import Optional

import config
from src.cache import APICache

logger = logging.getLogger(__name__)


def _create_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Crea una sesión HTTP con retry y backoff exponencial."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class WorldCupClient:
    """Cliente para la World Cup API (api.worldcupapi.com)."""

    def __init__(self, api_key: str = None, lang: str = None):
        self.api_key = api_key or config.WORLD_CUP_API_KEY
        self.lang = lang or config.WORLD_CUP_LANG
        self.base_url = config.WORLD_CUP_API_BASE
        self.cache = APICache()
        self.session = _create_session()

        if not self.api_key:
            logger.warning("⚠️  WORLD_CUP_API_KEY no configurada. Las llamadas devolverán None.")

    def _request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Realiza una petición GET. Inyecta key y lang automáticamente."""
        full_params = {"key": self.api_key, "lang": self.lang, **params}
        try:
            url = f"{self.base_url}/{endpoint}"
            response = self.session.get(url, params=full_params, timeout=15)
            response.raise_for_status()
            remaining = response.headers.get("x-requests-remaining", "?")
            logger.info(f"✅ World Cup API /{endpoint} — requests restantes: {remaining}")
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ World Cup API HTTP error en /{endpoint}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ World Cup API connection error en /{endpoint}: {e}")
            return None
        except ValueError as e:  # JSON inválido
            logger.error(f"❌ World Cup API JSON inválido en /{endpoint}: {e}")
            return None

    def _cached_get(self, endpoint: str, params: dict, ttl: int, cache_key: str):
        """Flujo común: key vacía → None; caché → _request → cache.set."""
        if not self.api_key:
            return None
        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            logger.info(f"✅ /{endpoint} desde caché — 0 requests")
            return cached
        data = self._request(endpoint, params)
        if data is None:
            return None
        self.cache.set(cache_key, data)
        return data

    def get_livescores(self):
        """Marcadores en vivo. GET /livescores."""
        return self._cached_get(
            "livescores", {}, config.CACHE_TTL_WC_LIVE,
            f"wc_livescores_{self.lang}",
        )
```

- [ ] **Step 4: Ejecutar los tests para verificar que pasan**

Run: `pytest tests/test_worldcup_client.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/worldcup_client.py tests/test_worldcup_client.py
git commit -m "feat(worldcup): esqueleto del cliente + get_livescores"
```

---

### Task 3: Fixtures y clasificaciones

`get_fixtures`, `get_standings`, `get_live_standings`.

**Files:**
- Modify: `src/worldcup_client.py` (añadir métodos a la clase)
- Test: `tests/test_worldcup_client.py` (añadir tests)

- [ ] **Step 1: Añadir los tests que fallan**

Añadir al final de `tests/test_worldcup_client.py`:

```python
def test_fixtures_optional_params_omitted(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({"r": []}))
    c.get_fixtures(group="A")
    _, kwargs = c.session.get.call_args
    p = kwargs["params"]
    assert p["group"] == "A"
    assert "team_id" not in p and "date" not in p


def test_fixtures_team_and_date(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_fixtures(team_id=1443, date="2026-06-11")
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/fixtures")
    assert kwargs["params"]["team_id"] == 1443
    assert kwargs["params"]["date"] == "2026-06-11"
    assert "group" not in kwargs["params"]


def test_standings_form_flag(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_standings(group="B", form=True)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/standings")
    assert kwargs["params"]["group"] == "B"
    assert kwargs["params"]["form"] == 1


def test_standings_no_form_by_default(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_standings(group="C")
    _, kwargs = c.session.get.call_args
    assert "form" not in kwargs["params"]


def test_live_standings_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_live_standings("A")
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/livestandings")
    assert kwargs["params"]["group"] == "A"
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest tests/test_worldcup_client.py -k "fixtures or standings" -v`
Expected: FAIL con `AttributeError: 'WorldCupClient' object has no attribute 'get_fixtures'`

- [ ] **Step 3: Implementar los métodos**

Añadir a la clase `WorldCupClient` en `src/worldcup_client.py` (tras `get_livescores`):

```python
    def get_fixtures(self, group=None, team_id=None, date=None):
        """Partidos / calendario. GET /fixtures (group, team_id o date opcionales)."""
        params = {}
        if group is not None:
            params["group"] = group
        if team_id is not None:
            params["team_id"] = team_id
        if date is not None:
            params["date"] = date
        cache_key = f"wc_fixtures_{group}_{team_id}_{date}_{self.lang}"
        return self._cached_get("fixtures", params, config.CACHE_TTL_WC_FIXTURES, cache_key)

    def get_standings(self, group, form=False):
        """Clasificación de grupo. GET /standings (form=1 añade racha)."""
        params = {"group": group}
        if form:
            params["form"] = 1
        cache_key = f"wc_standings_{group}_{int(form)}_{self.lang}"
        return self._cached_get("standings", params, config.CACHE_TTL_WC_STANDINGS, cache_key)

    def get_live_standings(self, group):
        """Clasificación en vivo. GET /livestandings."""
        return self._cached_get(
            "livestandings", {"group": group}, config.CACHE_TTL_WC_LIVE,
            f"wc_livestandings_{group}_{self.lang}",
        )
```

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest tests/test_worldcup_client.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add src/worldcup_client.py tests/test_worldcup_client.py
git commit -m "feat(worldcup): fixtures, standings y livestandings"
```

---

### Task 4: Datos por partido

`get_commentary`, `get_events`, `get_statistics`, `get_lineups`.

**Files:**
- Modify: `src/worldcup_client.py`
- Test: `tests/test_worldcup_client.py`

- [ ] **Step 1: Añadir los tests que fallan**

Añadir al final de `tests/test_worldcup_client.py`:

```python
def test_commentary_with_from_to(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_commentary(335680, from_=1000, to=2000)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/commentary")
    p = kwargs["params"]
    assert p["match_id"] == 335680
    assert p["from"] == 1000
    assert p["to"] == 2000


def test_commentary_omits_optional(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_commentary(335680)
    _, kwargs = c.session.get.call_args
    assert "from" not in kwargs["params"] and "to" not in kwargs["params"]


def test_events_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_events(335680)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/events")
    assert kwargs["params"]["match_id"] == 335680


def test_statistics_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_statistics(335680)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/statistics")
    assert kwargs["params"]["match_id"] == 335680


def test_lineups_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_lineups(335680)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/lineups")
    assert kwargs["params"]["match_id"] == 335680
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest tests/test_worldcup_client.py -k "commentary or events or statistics or lineups" -v`
Expected: FAIL con `AttributeError: ... has no attribute 'get_commentary'`

- [ ] **Step 3: Implementar los métodos**

Añadir a la clase `WorldCupClient`:

```python
    def get_commentary(self, match_id, from_=None, to=None):
        """Narración minuto a minuto. GET /commentary (from/to en segundos)."""
        params = {"match_id": match_id}
        if from_ is not None:
            params["from"] = from_
        if to is not None:
            params["to"] = to
        cache_key = f"wc_commentary_{match_id}_{from_}_{to}_{self.lang}"
        return self._cached_get("commentary", params, config.CACHE_TTL_WC_MATCH, cache_key)

    def get_events(self, match_id):
        """Goles, tarjetas y cambios. GET /events."""
        return self._cached_get(
            "events", {"match_id": match_id}, config.CACHE_TTL_WC_MATCH,
            f"wc_events_{match_id}_{self.lang}",
        )

    def get_statistics(self, match_id):
        """Estadísticas del partido. GET /statistics (la API ignora lang aquí)."""
        return self._cached_get(
            "statistics", {"match_id": match_id}, config.CACHE_TTL_WC_MATCH,
            f"wc_statistics_{match_id}_{self.lang}",
        )

    def get_lineups(self, match_id):
        """Alineaciones. GET /lineups."""
        return self._cached_get(
            "lineups", {"match_id": match_id}, config.CACHE_TTL_WC_MATCH,
            f"wc_lineups_{match_id}_{self.lang}",
        )
```

- [ ] **Step 4: Ejecutar para verificar que pasan**

Run: `pytest tests/test_worldcup_client.py -v`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add src/worldcup_client.py tests/test_worldcup_client.py
git commit -m "feat(worldcup): commentary, events, statistics y lineups"
```

---

### Task 5: Datos estáticos / históricos

`get_squad`, `get_history`, `get_head2head`, `get_top_scorers`, `get_cards`.

**Files:**
- Modify: `src/worldcup_client.py`
- Test: `tests/test_worldcup_client.py`

- [ ] **Step 1: Añadir los tests que fallan**

Añadir al final de `tests/test_worldcup_client.py`:

```python
def test_squad_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_squad(1443)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/squads")
    assert kwargs["params"]["team_id"] == 1443


def test_history_optional_params(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_history(date_from="2022-11-01", date_to="2022-12-31")
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/history")
    p = kwargs["params"]
    assert p["date_from"] == "2022-11-01"
    assert p["date_to"] == "2022-12-31"
    assert "team_id" not in p


def test_history_by_team(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_history(team_id=1443)
    _, kwargs = c.session.get.call_args
    assert kwargs["params"]["team_id"] == 1443
    assert "date_from" not in kwargs["params"]


def test_head2head_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_head2head(208, 211)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/head2head")
    assert kwargs["params"]["team1_id"] == 208
    assert kwargs["params"]["team2_id"] == 211


def test_top_scorers_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_top_scorers()
    args, _ = c.session.get.call_args
    assert args[0].endswith("/goalscorers")


def test_cards_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_cards()
    args, _ = c.session.get.call_args
    assert args[0].endswith("/cards")
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

Run: `pytest tests/test_worldcup_client.py -k "squad or history or head2head or scorers or cards" -v`
Expected: FAIL con `AttributeError: ... has no attribute 'get_squad'`

- [ ] **Step 3: Implementar los métodos**

Añadir a la clase `WorldCupClient`:

```python
    def get_squad(self, team_id):
        """Plantilla de una selección. GET /squads."""
        return self._cached_get(
            "squads", {"team_id": team_id}, config.CACHE_TTL_WC_STATIC,
            f"wc_squads_{team_id}_{self.lang}",
        )

    def get_history(self, date_from=None, date_to=None, team_id=None):
        """Partidos finalizados. GET /history (date_from/date_to/team_id opcionales)."""
        params = {}
        if date_from is not None:
            params["date_from"] = date_from
        if date_to is not None:
            params["date_to"] = date_to
        if team_id is not None:
            params["team_id"] = team_id
        cache_key = f"wc_history_{date_from}_{date_to}_{team_id}_{self.lang}"
        return self._cached_get("history", params, config.CACHE_TTL_WC_STATIC, cache_key)

    def get_head2head(self, team1_id, team2_id):
        """Cara a cara histórico entre dos selecciones. GET /head2head."""
        params = {"team1_id": team1_id, "team2_id": team2_id}
        cache_key = f"wc_head2head_{team1_id}_{team2_id}_{self.lang}"
        return self._cached_get("head2head", params, config.CACHE_TTL_WC_STATIC, cache_key)

    def get_top_scorers(self):
        """Máximos goleadores. GET /goalscorers."""
        return self._cached_get(
            "goalscorers", {}, config.CACHE_TTL_WC_STATIC,
            f"wc_goalscorers_{self.lang}",
        )

    def get_cards(self):
        """Ranking de tarjetas (rojas/amarillas). GET /cards."""
        return self._cached_get(
            "cards", {}, config.CACHE_TTL_WC_STATIC,
            f"wc_cards_{self.lang}",
        )
```

- [ ] **Step 4: Ejecutar la suite completa**

Run: `pytest tests/test_worldcup_client.py -v`
Expected: PASS (22 tests)

- [ ] **Step 5: Commit**

```bash
git add src/worldcup_client.py tests/test_worldcup_client.py
git commit -m "feat(worldcup): squads, history, head2head, goalscorers y cards"
```

---

### Task 6: Plantilla `.env.example` y verificación final

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Añadir el placeholder en `.env.example`**

Leer primero `.env.example` para localizar el bloque de keys de fútbol y añadir, en una zona coherente:

```bash
# World Cup API (fútbol) — https://worldcupapi.com
WORLD_CUP_API_KEY=
```

- [ ] **Step 2: Ejecutar la suite completa del proyecto**

Run: `pytest tests/test_worldcup_client.py -v`
Expected: PASS (22 tests)

- [ ] **Step 3: Verificación de regresión global**

Run: `pytest -q`
Expected: toda la suite del repo sigue en verde (el cliente nuevo no toca código existente salvo `config.py`).

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "docs(env): placeholder WORLD_CUP_API_KEY en .env.example"
```

---

## Notas de implementación

- **No reiniciar PM2** durante el desarrollo: este cliente aún no se engancha al bot/daemon, así que no hay servicio que recargar. (La regla de reiniciar `winstake-bot`/`winstake-api` aplica cuando se cambia código en producción del backend.)
- El parseo es deliberadamente crudo (devuelve el JSON tal cual). Cuando se integre en el motor de picks o el dashboard se añadirá normalización del shape — eso es otro spec/plan.
