# BLOQUE C — Settle daemon ampliado para persistir match_outcomes

## Estado actual

### Flujo completo del settle daemon

```
settle_daemon.py  →  tick() cada 60 min (ventana 10:00–02:00)
                  →  settle_all()
                       ├── verify_results()            [LaLiga]
                       │     FootballClient → API-Football
                       │     Cierra value_bets pendientes LaLiga
                       │     Escribe: match_results + value_bets.result
                       │
                       └── run_backtesting_check()     [NBA]
                             nba_resolver.py
                             Escribe: match_results + value_bets.result
```

### run_backtesting_check() — flujo interno NBA

1. Query: `value_bets JOIN analyses LEFT JOIN match_results` donde
   `match_results.id IS NULL AND run_date < now-24h AND sport='nba'`
2. Para cada value_bet pendiente: llama `_fetch_game_result_from_nba_api()`
   - 1 llamada LeagueGameFinder por equipo/fecha
   - `time.sleep(0.6)` entre llamadas (rate limit)
   - Con 127 picks = ~76 segundos de espera mínima
3. Determina WIN/LOSS/PUSH con `_determine_result()`
4. INSERTs en `match_results`, UPDATE `value_bets.result/pnl_units/settled_at`

### Lo que NO hace el daemon hoy

- No toca `match_outcomes` (tabla nueva, no existía antes)
- No procesa los 344 análisis NBA que NO generaron value_bets
- No deduplica: si el mismo partido tiene 18 value_bets, hace 18
  llamadas a nba_api para el mismo partido

## Problema

Los 344 análisis NBA sin value_bet (EV < 3%) representan predicciones
del modelo para las que nunca registramos el resultado real. Sin ese
dato, el dataset de calibración queda sesgado: solo tenemos outcomes
de los partidos donde el modelo vio valor, precisamente los de mayor
confianza, que es donde la sobreconfianza es mayor.

## Solución propuesta

Añadir al ciclo de settle una llamada a `persist_nba_outcomes()` que:
1. Hace UNA sola llamada LeagueGameFinder (toda la temporada)
2. Popula `match_outcomes` para todos los análisis con commence_time pasado
3. No toca el flujo existente de value_bets / match_results

El flujo resultante:

```
settle_all()
  ├── verify_results()            [LaLiga — sin cambios]
  ├── run_backtesting_check()     [NBA value_bets — sin cambios]
  └── persist_nba_outcomes()      [NBA match_outcomes — NUEVO]
        historical_results.run()
        1 llamada API → toda la temporada
        INSERT OR IGNORE en match_outcomes
```

## Flujo nuevo — pseudocódigo

```python
# En settle_daemon.py → settle_all()
def settle_all() -> dict:
    summary = {"laliga": None, "nba": None, "nba_outcomes": None}

    # [sin cambios] LaLiga value_bets
    if config.LALIGA_ENABLED:
        summary["laliga"] = verify_results()

    # [sin cambios] NBA value_bets → match_results
    summary["nba"] = run_backtesting_check(str(DB_PATH))

    # [NUEVO] NBA analyses → match_outcomes (todos, no solo con picks)
    try:
        from src.historical_results import run as persist_outcomes_run
        persist_outcomes_run(sport="nba", season=NBA_SEASON, db_path=str(DB_PATH))
        summary["nba_outcomes"] = "ok"
    except Exception as e:
        logger.error(f"Error persistiendo match_outcomes: {e}", exc_info=True)
        summary["nba_outcomes"] = {"error": str(e)}

    return summary
```

## Por qué esta arquitectura

**Una llamada, no N:** `historical_results.run()` descarga toda la
temporada en una sola petición a LeagueGameFinder. El resolver actual
hace 1 petición por partido (×127 picks = 76s). La nueva función
hace 1 petición total y luego matchea localmente.

**Idempotente:** `persist_outcomes()` usa `INSERT OR IGNORE` por
`UNIQUE(home_team, away_team, game_date)`. Ejecutar 60 veces al día
no crea duplicados.

**Sin acoplamiento:** `historical_results.py` no conoce el settle
daemon. El daemon simplemente llama `run()`. Si falla, el resto del
settle no se interrumpe (bloque try/except aislado).

**No rompe el flujo existente:** `run_backtesting_check()` sigue
cerrando value_bets exactamente igual. `match_outcomes` es adicional.

## Decisiones de diseño pendientes de confirmar

1. **¿Cuándo ejecutar `persist_nba_outcomes()`?** Propuesta: en cada
   tick, después de `run_backtesting_check()`. Coste: ~1-2s por tick
   (1 llamada API, matching local). Aceptable.

2. **¿Importar `NBA_SEASON` de `nba_resolver` o de config?**
   Actualmente `NBA_SEASON = "2025-26"` está hardcodeado en
   `nba_resolver.py`. Para evitar duplicarlo, el settle podría
   importarlo desde allí o moverlo a `config.py`.

3. **¿Loggear cuántos outcomes se insertaron en cada tick?**
   Recomendado: sí, para monitoreo desde `pm2 logs winstake-settle`.

## Archivos a modificar

| Archivo | Cambio |
|---|---|
| `src/settle_daemon.py` | Añadir llamada a `persist_nba_outcomes()` en `settle_all()` |
| `src/historical_results.py` | Sin cambios (ya funciona como se necesita) |

## Test a escribir

```python
def test_settle_all_persists_nba_outcomes(tmp_path, monkeypatch):
    """settle_all() llama a historical_results.run() y persiste outcomes."""
    called = []

    def mock_run(**kwargs):
        called.append(kwargs)

    monkeypatch.setattr("src.settle_daemon.historical_results_run", mock_run)
    monkeypatch.setattr("src.settle_daemon.verify_results", lambda: {})
    monkeypatch.setattr("src.settle_daemon.run_backtesting_check", lambda p: {})

    from src.settle_daemon import settle_all
    settle_all()

    assert len(called) == 1
    assert called[0]["sport"] == "nba"
```

## Estimación de trabajo

- `src/settle_daemon.py`: ~10 líneas
- Test: ~20 líneas
- Total: ~30 min incluyendo `pm2 restart` y verificación de logs
