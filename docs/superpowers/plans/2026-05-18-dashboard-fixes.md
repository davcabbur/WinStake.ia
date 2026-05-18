# Dashboard Fixes — ROI y Filtro NBA

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corregir dos bugs del dashboard: ROI calculado sobre número de apuestas en lugar de stake real, e historial que muestra picks de LaLiga (deshabilitada).

**Architecture:** Dos cambios independientes. El bug de ROI requiere modificar el backend para incluir `total_staked` en la respuesta y el frontend para usar ese valor. El bug del historial es solo un filtro `WHERE` en la query SQL del backend; opcionalmente se añade un parámetro `sport` para que el endpoint sea reutilizable.

**Tech Stack:** Python/FastAPI (`src/api/routes.py`), Angular 18 standalone (`frontend/src/app/features/dashboard/components/stats-cards/stats-cards.component.ts`)

---

## Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `src/api/routes.py:23-50` | Añadir JOIN a `value_bets` y devolver `total_staked` |
| `frontend/src/app/features/dashboard/components/stats-cards/stats-cards.component.ts:107-117` | Usar `total_staked` del backend; renombrar label |
| `src/api/routes.py:52-75` | Añadir `WHERE vb.sport = ?` con parámetro `sport` |
| `tests/test_dashboard_api.py` (nuevo) | Tests de integración para ambos endpoints |

---

## Task 1: Fix ROI — backend devuelve `total_staked`

**Problema:** `/api/dashboard/stats` consulta solo `match_results` y no devuelve `total_staked`. El frontend compensa con `(profit / totalBets) * 100`, que es incorrecto.

**Files:**
- Modify: `src/api/routes.py:23-50`
- Create: `tests/test_dashboard_api.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_dashboard_api.py
import pytest
from fastapi.testclient import TestClient
import sqlite3
import tempfile
import os

# Patch DB_PATH antes de importar la app
@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("WINSTAKE_DB_PATH", db_path)
    import src.api.routes as routes_module
    monkeypatch.setattr(routes_module, "DB_PATH", db_path)
    
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE analyses (
            id INTEGER PRIMARY KEY,
            run_date TEXT,
            home_team TEXT,
            away_team TEXT,
            commence_time TEXT
        );
        CREATE TABLE value_bets (
            id INTEGER PRIMARY KEY,
            analysis_id INTEGER,
            selection TEXT,
            odds REAL,
            ev_percent REAL,
            confidence TEXT,
            stake_units REAL,
            sport TEXT DEFAULT 'nba',
            is_paper INTEGER DEFAULT 1
        );
        CREATE TABLE match_results (
            id INTEGER PRIMARY KEY,
            value_bet_id INTEGER,
            bet_won INTEGER,
            profit_units REAL,
            recorded_at TEXT
        );
        INSERT INTO analyses VALUES (1, '2026-05-01', 'Lakers', 'Celtics', '2026-05-01T20:00:00Z');
        INSERT INTO value_bets VALUES (1, 1, 'Lakers ML', 1.90, 5.0, 'high', 2.0, 'nba', 1);
        INSERT INTO match_results VALUES (1, 1, 1, 0.9, '2026-05-02T10:00:00');
    """)
    conn.commit()
    conn.close()
    return db_path

def get_test_client(tmp_db):
    from main import app
    return TestClient(app)

def test_stats_includes_total_staked(tmp_db):
    client = get_test_client(tmp_db)
    resp = client.get("/api/dashboard/stats", headers={"X-API-Key": "test"})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_staked" in data
    assert data["total_staked"] == pytest.approx(2.0)

def test_stats_roi_uses_staked_not_count(tmp_db):
    """ROI = profit/staked, no profit/total_bets."""
    client = get_test_client(tmp_db)
    resp = client.get("/api/dashboard/stats", headers={"X-API-Key": "test"})
    data = resp.json()
    # profit=0.9, staked=2.0 → ROI=45%, no 90% (profit/1_bet)
    assert data["total_staked"] == pytest.approx(2.0)
    assert data["total_profit"] == pytest.approx(0.9)
```

- [ ] **Step 2: Verificar que el test falla**

```
pytest tests/test_dashboard_api.py::test_stats_includes_total_staked -v
```
Esperado: `FAILED` — `KeyError: 'total_staked'` o similar.

- [ ] **Step 3: Modificar la query del backend**

En `src/api/routes.py`, reemplazar el bloque `@router.get("/dashboard/stats")` (líneas 23–50) por:

```python
@router.get("/dashboard/stats")
def get_dashboard_stats():
    """Devuelve estadísticas agregadas de ROI, winrate y profit."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT 
                COUNT(mr.id) as total_bets,
                SUM(CASE WHEN mr.bet_won = 1 THEN 1 ELSE 0 END) as won_bets,
                SUM(mr.profit_units) as total_profit,
                SUM(vb.stake_units) as total_staked
            FROM match_results mr
            JOIN value_bets vb ON vb.id = mr.value_bet_id
        """)
        row = cursor.fetchone()

        total_bets = row["total_bets"] or 0
        won_bets = row["won_bets"] or 0
        total_profit = row["total_profit"] or 0.0
        total_staked = row["total_staked"] or 0.0
        win_rate = (won_bets / total_bets * 100) if total_bets > 0 else 0.0

        return {
            "total_bets": total_bets,
            "won_bets": won_bets,
            "win_rate": round(win_rate, 2),
            "total_profit": round(total_profit, 2),
            "total_staked": round(total_staked, 2),
        }
    finally:
        conn.close()
```

- [ ] **Step 4: Pasar los tests**

```
pytest tests/test_dashboard_api.py::test_stats_includes_total_staked tests/test_dashboard_api.py::test_stats_roi_uses_staked_not_count -v
```
Esperado: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/api/routes.py tests/test_dashboard_api.py
git commit -m "fix: dashboard/stats devuelve total_staked para ROI correcto"
```

---

## Task 2: Fix ROI — frontend usa `total_staked`

**Files:**
- Modify: `frontend/src/app/features/dashboard/components/stats-cards/stats-cards.component.ts:107-117`

- [ ] **Step 1: Modificar `ngOnChanges` y el template**

En `stats-cards.component.ts`, reemplazar el bloque `ngOnChanges` (líneas 107–116) y las líneas del template que muestran ROI:

```typescript
ngOnChanges() {
  if (this.stats) {
    this.totalBets = this.stats.total_bets || 0;
    this.wonBets = this.stats.won_bets || 0;
    this.winRate = this.stats.win_rate || 0;
    this.profit = this.stats.total_profit || 0;
    const staked = this.stats.total_staked || 0;
    this.roi = staked > 0 ? (this.profit / staked) * 100 : 0;
  }
}
```

En el mismo archivo, reemplazar el bloque de la tarjeta "ROI Estimado" en el template (líneas 34–45):

```html
<div class="glass-card stat-card">
  <div class="stat-header">
    <span class="icon">💰</span>
    <h3>ROI</h3>
  </div>
  <div class="stat-value" [class.positive]="roi > 0" [class.negative]="roi < 0">
    {{ roi > 0 ? '+' : '' }}{{ roi | number:'1.1-1' }}%
  </div>
  <div class="stat-sub">
    Sobre {{ stats?.total_staked | number:'1.1-1' }} u. apostadas
  </div>
</div>
```

- [ ] **Step 2: Compilar Angular**

```
cd frontend && npx ng build --configuration development 2>&1 | tail -5
```
Esperado: `Build at:` sin errores.

- [ ] **Step 3: Verificar visualmente**

Arrancar el frontend:
```
cd frontend && npx ng serve --port 4200
```
Abrir `http://localhost:4200`. La tarjeta "ROI" debe mostrar el valor calculado sobre stake (≈ -7.75%) en lugar del valor anterior (≈ -34.8%). El sub-texto debe decir "Sobre X u. apostadas".

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/features/dashboard/components/stats-cards/stats-cards.component.ts
git commit -m "fix: ROI en dashboard calculado sobre stake real, no número de apuestas"
```

---

## Task 3: Fix historial — filtrar solo NBA

**Problema:** La query de `/api/dashboard/history` no filtra por `vb.sport`, por lo que incluye picks de LaLiga (deshabilitada desde commit `11fd25b`).

**Files:**
- Modify: `src/api/routes.py:52-75`
- Test: `tests/test_dashboard_api.py` (añadir al archivo creado en Task 1)

- [ ] **Step 1: Añadir el test que falla**

Añadir al final de `tests/test_dashboard_api.py`:

```python
def test_history_excludes_laliga(tmp_db):
    """El historial solo devuelve picks NBA, no LaLiga."""
    conn = sqlite3.connect(tmp_db)
    conn.executescript("""
        INSERT INTO analyses VALUES (2, '2026-05-01', 'Getafe', 'Mallorca', '2026-05-01T16:00:00Z');
        INSERT INTO value_bets VALUES (2, 2, 'Getafe ML', 2.10, 4.0, 'medium', 1.5, 'laliga', 1);
    """)
    conn.commit()
    conn.close()

    client = get_test_client(tmp_db)
    resp = client.get("/api/dashboard/history", headers={"X-API-Key": "test"})
    assert resp.status_code == 200
    rows = resp.json()["data"]
    teams = {(r["home_team"], r["away_team"]) for r in rows}
    assert ("Getafe", "Mallorca") not in teams
    assert ("Lakers", "Celtics") in teams

def test_history_sport_param(tmp_db):
    """El parámetro sport filtra correctamente."""
    conn = sqlite3.connect(tmp_db)
    conn.executescript("""
        INSERT INTO analyses VALUES (3, '2026-05-01', 'Getafe', 'Mallorca', '2026-05-01T16:00:00Z');
        INSERT INTO value_bets VALUES (3, 3, 'Getafe ML', 2.10, 4.0, 'medium', 1.5, 'laliga', 1);
    """)
    conn.commit()
    conn.close()

    client = get_test_client(tmp_db)
    resp = client.get("/api/dashboard/history?sport=laliga", headers={"X-API-Key": "test"})
    rows = resp.json()["data"]
    teams = {(r["home_team"], r["away_team"]) for r in rows}
    assert ("Getafe", "Mallorca") in teams
```

- [ ] **Step 2: Verificar que fallan**

```
pytest tests/test_dashboard_api.py::test_history_excludes_laliga -v
```
Esperado: `FAILED` — Getafe/Mallorca aparece cuando no debería.

- [ ] **Step 3: Modificar el endpoint**

En `src/api/routes.py`, reemplazar la función `get_bet_history` (líneas 52–75) por:

```python
@router.get("/dashboard/history")
def get_bet_history(limit: int = 50, offset: int = 0, sport: str = "nba"):
    """Devuelve el historial de apuestas filtrado por sport (default: nba)."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT 
                a.run_date, a.home_team, a.away_team, a.commence_time,
                vb.selection, vb.odds, vb.ev_percent, vb.confidence, vb.stake_units,
                mr.bet_won, mr.profit_units
            FROM value_bets vb
            JOIN analyses a ON vb.analysis_id = a.id
            LEFT JOIN match_results mr ON vb.id = mr.value_bet_id
            WHERE vb.sport = ?
            ORDER BY a.run_date DESC
            LIMIT ? OFFSET ?
        """, (sport, limit, offset))

        rows = cursor.fetchall()
        history = [dict(row) for row in rows]

        return {"data": history, "limit": limit, "offset": offset, "sport": sport}
    finally:
        conn.close()
```

- [ ] **Step 4: Pasar los tests**

```
pytest tests/test_dashboard_api.py -v
```
Esperado: todos los tests del archivo en `PASSED`.

- [ ] **Step 5: Pasar la suite completa**

```
pytest --tb=short -q
```
Esperado: sin regresiones (201 tests previos + los nuevos).

- [ ] **Step 6: Commit**

```bash
git add src/api/routes.py tests/test_dashboard_api.py
git commit -m "fix: historial filtrado por sport=nba por defecto, LaLiga excluida"
```

---

## Task 4: Arrancar servicios y verificar en vivo

- [ ] **Step 1: Arrancar la API**

```
pm2 start "python main.py" --name winstake-api --interpreter python
pm2 start "python src/bot_daemon.py" --name winstake-bot --interpreter python
pm2 save
pm2 status
```
Esperado: ambos procesos en `online`.

- [ ] **Step 2: Verificar endpoint stats en vivo**

```
curl -s -H "X-API-Key: $WINSTAKE_API_KEY" http://localhost:8000/api/dashboard/stats | python -m json.tool
```
Verificar que la respuesta incluye `total_staked` con un valor numérico real.

- [ ] **Step 3: Verificar historial en vivo**

```
curl -s -H "X-API-Key: $WINSTAKE_API_KEY" "http://localhost:8000/api/dashboard/history?limit=5" | python -m json.tool
```
Verificar que ninguna fila tiene `home_team` o `away_team` de LaLiga (Getafe, Mallorca, etc.).

- [ ] **Step 4: Verificar frontend en vivo**

Abrir `http://localhost:4200`. Confirmar:
- Tarjeta "ROI" muestra ≈ -7.75% (no -34.8%)
- Sub-texto dice "Sobre X u. apostadas"
- Historial no muestra Getafe vs Mallorca ni otros partidos de LaLiga

---

## Self-Review

**Cobertura del spec:**
- ✅ ROI discrepancia: backend añade `total_staked` (Task 1), frontend lo usa (Task 2)
- ✅ Filtrar solo NBA en historial (Task 3)
- ✅ Verificación en vivo (Task 4)

**Items de PENDING.md NO incluidos en este plan (requieren sesiones dedicadas):**
- Tailscale como servicio Windows — no es código; ejecutar `tailscale.exe service install` con permisos de admin
- MagicDNS — prueba manual desde otro dispositivo de la red Tailscale
- Recalibración del modelo Normal — requiere análisis estadístico + datos de calibración
- Dashboard V1-V5 — plan separado por tamaño

**Placeholders:** ninguno — todo el código está completo.

**Consistencia de tipos:**
- `total_staked` devuelto como `float` por el backend → consumido como `number` en TypeScript ✅
- `sport` es `str` en query param y en columna SQLite ✅
