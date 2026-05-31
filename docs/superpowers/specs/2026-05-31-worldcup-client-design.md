# WorldCupClient — Cliente Python para la World Cup API

**Fecha:** 2026-05-31
**Estado:** Aprobado (pendiente de plan de implementación)

## Objetivo

Añadir un cliente Python (`src/worldcup_client.py`) para [worldcupapi.com](https://api.worldcupapi.com)
que cubra los 13 endpoints de la API, siguiendo el patrón ya establecido en el
repo por `OddsClient` y `FootballClient`. La key vive en `.env` como
`WORLD_CUP_API_KEY` (free trial, **tope de 1500 requests** → caché agresiva
obligatoria).

## Decisiones de diseño

- **Alcance:** los 13 endpoints completos.
- **Sin modo mock.** La key ya está configurada. Si falta o falla la API, los
  métodos devuelven `[]`/`None` y loggean; no hay datos simulados (a diferencia
  de `FootballClient`/`OddsClient`).
- **Idioma por defecto `es`.** La API acepta `&lang=`; se añade automáticamente
  a toda request. Configurable vía `WINSTAKE_WC_LANG`.
- **Parseo defensivo.** No hay JSON de ejemplo (las colecciones Postman traen
  `"response": []`). El parseo usa `.get()` encadenado sin asumir estructura
  exacta y devuelve el JSON normalizado. El shape fino se ajusta tras la primera
  llamada real.

## Arquitectura

Calca el patrón existente (no se introduce arquitectura nueva):

- Sesión `requests.Session` con retry/backoff exponencial (helper
  `_create_session`, idéntico a los otros clientes: total=3, backoff=0.5,
  status_forcelist=[500,502,503,504], solo GET).
- Caché en disco vía `src.cache.APICache` (misma que el resto).
- Logging en español con emojis, igual que el resto del repo.

### Config nueva (`config.py`)

```python
WORLD_CUP_API_KEY  = os.getenv("WORLD_CUP_API_KEY", "")
WORLD_CUP_API_BASE = "https://api.worldcupapi.com"
WORLD_CUP_LANG     = os.getenv("WINSTAKE_WC_LANG", "es")

# TTLs calibrados para no quemar las 1500 requests:
CACHE_TTL_WC_LIVE      = 60          # livescores / livestandings (en vivo)
CACHE_TTL_WC_FIXTURES  = 6 * 3600    # fixtures (calendario, cambia poco)
CACHE_TTL_WC_STANDINGS = 30 * 60     # standings
CACHE_TTL_WC_MATCH     = 5 * 60      # events / statistics / lineups / commentary
CACHE_TTL_WC_STATIC    = 24 * 3600   # squads / history / head2head / goalscorers / cards
```

### Clase `WorldCupClient`

- `__init__(self, api_key=None, lang=None)`:
  - `self.api_key = api_key or config.WORLD_CUP_API_KEY`
  - `self.lang = lang or config.WORLD_CUP_LANG`
  - `self.base_url`, `self.cache = APICache()`, `self.session = _create_session()`
  - Si `api_key` vacía → `logger.warning(...)`. **No** hay `_mock_mode`; los
    métodos cortan devolviendo `[]`/`None` cuando la key está vacía.

- `_request(self, endpoint, params)` (privado):
  - Inyecta `key` y `lang` en `params` automáticamente.
  - `GET {base_url}/{endpoint}`, `timeout=15`.
  - Loggea `x-requests-remaining` del header si la API lo expone (clave con tope
    de 1500).
  - Captura `HTTPError`/`RequestException` → loggea y devuelve `None`. Nunca
    propaga la excepción al llamante.

- Patrón de cada método público:
  `key vacía → []/None` → `cache.get` → `_request` → parseo defensivo →
  `cache.set` → return. En error/JSON inválido: `[]`/`None` + log.

- **Cache key:** incluye endpoint + params relevantes + `lang` (para no mezclar
  idiomas en la misma entrada).

### Métodos (13 endpoints)

| Método | Endpoint | Params | TTL |
|--------|----------|--------|-----|
| `get_livescores()` | `/livescores` | — | LIVE |
| `get_fixtures(group=None, team_id=None, date=None)` | `/fixtures` | uno opcional | FIXTURES |
| `get_standings(group, form=False)` | `/standings` | `group`, `form=1` | STANDINGS |
| `get_live_standings(group)` | `/livestandings` | `group` | LIVE |
| `get_commentary(match_id, from_=None, to=None)` | `/commentary` | `match_id`,`from`,`to` | MATCH |
| `get_events(match_id)` | `/events` | `match_id` | MATCH |
| `get_statistics(match_id)` | `/statistics` | `match_id` | MATCH |
| `get_lineups(match_id)` | `/lineups` | `match_id` | MATCH |
| `get_squad(team_id)` | `/squads` | `team_id` | STATIC |
| `get_history(date_from=None, date_to=None, team_id=None)` | `/history` | opcionales | STATIC |
| `get_head2head(team1_id, team2_id)` | `/head2head` | `team1_id`,`team2_id` | STATIC |
| `get_top_scorers()` | `/goalscorers` | — | STATIC |
| `get_cards()` | `/cards` | — | STATIC |

Nota: `get_statistics` no admite `lang` según la colección Postman
("no translations possible"); el cliente lo envía igual (la API lo ignora) para
mantener uniformidad — sin caso especial.

## Flujo de datos

`bot / dashboard → WorldCupClient.get_*() → APICache (hit?) → _request → API → parseo → cache.set → dict/list limpio`

## Manejo de errores

- Sin key → warning una vez en `__init__`; cada método devuelve `[]`/`None`.
- HTTP 4xx/5xx, timeout, conexión → log + `None` desde `_request`; el método
  público traduce a `[]`/`None`.
- JSON inesperado / `KeyError`/`TypeError` en parseo → log + `[]`/`None`.
- Ninguna excepción se propaga al llamante.

## Tests (`tests/test_worldcup_client.py`)

Con `unittest.mock` (patrón del repo; **no** hay `responses`/`requests-mock`).
Se parchea `session.get` con un `MagicMock` que devuelve un fake `Response`
(`.json()`, `.raise_for_status()`, `.headers`). **No** se pega a la API real
(no gastar requests).

Casos:
1. Key vacía → warning, métodos devuelven `[]`/`None`, **0 llamadas HTTP**.
2. Cada método construye endpoint + params correctos, incluyendo `key` y `lang=es`.
3. `form=True` añade `form=1`; params `None` se omiten de la query.
4. Segunda llamada idéntica → servida desde caché (**0 requests**); cache key
   varía con `lang`.
5. `HTTPError`/JSON inválido → `[]`/`None`, sin excepción propagada.

## Fuera de alcance (YAGNI)

- Integración en el motor de picks o el dashboard (proyecto aparte).
- Mapeo de nombres de equipo ↔ team_id (se hará al integrar, si hace falta).
- Normalización fina del shape de cada endpoint (se ajusta tras la 1ª llamada real).
