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
