# Convenciones de Tests — WinStake.ia

## Patrón de tests con dataclasses

Cuando una función accede a atributos de una dataclass, los tests
DEBEN usar:

1. Instancia real de la dataclass (preferido)
2. `MagicMock(spec=DataclassName)` (fallback aceptable)
3. NUNCA `MagicMock()` puro (acepta cualquier atributo, oculta bugs)

Si el constructor de la dataclass es complejo, crear un helper
`make_test_<classname>()` en `tests/conftest.py` o `tests/factories.py`
que produzca instancias válidas con defaults sensatos.

### Por qué importa

`MagicMock()` sin `spec` acepta `mock.cualquier_atributo` sin error,
incluso si ese atributo no existe en la clase real. El bug
`bb.confidence` (atributo de `MatchAnalysis` accedido sobre `EVResult`)
pasó los tests durante semanas porque `_make_analysis_mock` usaba
`bb = MagicMock()` con `bb.confidence = "HIGH"` seteado a mano.

### Ejemplo correcto

```python
# ✅ Instancia real — detecta AttributeError inmediatamente
from src.ev_calculator import EVResult
from src.analyzer import MatchAnalysis

ev = EVResult(selection="Home", probability=0.55, odds=1.95,
              ev=0.075, ev_percent=7.5, is_value=True)
analysis = MatchAnalysis(home_team="Lakers", away_team="Celtics",
                         best_bet=ev, confidence="Alta")
```

```python
# ✅ MagicMock con spec — acepta solo atributos que existen en la clase
bb = MagicMock(spec=EVResult)
bb.is_value = True
bb.selection = "Home"
bb.odds = 1.95
bb.ev_percent = 7.5
# bb.confidence  →  AttributeError (EVResult no tiene confidence)
```

```python
# ❌ MagicMock puro — silencia cualquier bug de atributo
bb = MagicMock()
bb.confidence = "HIGH"   # parece OK, pero EVResult no tiene este campo
```

---

## Lecciones aprendidas (24-26 mayo 2026)

En 48h se introdujeron 4 bugs en producción que los tests existentes no
detectaron. Patrones identificados:

### 1. Tests con casos fáciles enmascaran bugs en casos edge

Un test que pasa con el "happy path" no prueba que el código sea correcto:
prueba que es correcto **para ese caso**.

Regla: al añadir un test, preguntarse **"¿qué caso edge de mi dominio NO
está cubriendo este test?"**

Para dominio NBA en particular:
- **Timezone**: incluir partidos que cruzan medianoche UTC (20:00+ ET =
  00:00+ UTC del día siguiente). El resolver usaba `commence_time[:10]`
  para extraer la fecha, que daba `'2026-05-26'`, pero `match_outcomes`
  guardaba `game_date = '2026-05-25'` (zona ET). El test anterior solo
  probaba partidos a las 23:40 UTC (mismo día), que nunca fallaban.
- **Ventanas de tiempo**: incluir 1h, ~4h (límite de guardia), 24h, 240h.
  El cutoff de 4h sobre `commence_time` y el VOID de 14d son umbrales
  independientes; los tests deben cubrir ambos lados de cada uno.

```python
# ✅ Parametrizar con casos representativos del dominio real
@pytest.mark.parametrize("commence_utc,outcome_date,should_match", [
    ("2026-04-14T23:40:00Z", "2026-04-14", True),   # sin cruce medianoche
    ("2026-05-26T00:10:00Z", "2026-05-25", True),   # cruce medianoche UTC/ET
    ("2026-04-15T02:30:00Z", "2026-04-14", True),   # cruce a las 02:30 UTC
    ("2026-04-14T23:40:00Z", None,         False),  # sin outcome en BD
])
```

### 2. "Igual de bien que antes" no es validación

El refactor `4077b5c` (resolver lee `match_outcomes`) resolvió el partido
Charlotte correctamente (19:40 ET = 23:40 UTC, sin cruce de medianoche) y
se declaró éxito. La prueba real era el siguiente partido típico de playoffs
(20:10 ET = 00:10 UTC del día siguiente), que quedó en `Pendiente` eterno.

Antes de declarar un refactor completo: validar con **al menos un caso
que use la funcionalidad modificada en su forma más exigente**, no el más
simple.

### 3. Tests unitarios pasan, integración end-to-end falla

Un test de unidad puede pasar y aun así el flujo completo estar roto si:
- El orden de ejecución de las fases importa (el resolver corría antes de
  que el outcome estuviera en BD en el mismo tick)
- La lógica de integración entre módulos no está cubierta

Antes de declarar "feature completa": validar **al menos un caso real
end-to-end** en producción (restart del daemon + comprobar BD + ver logs).
