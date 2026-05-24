# Pendientes - WinStake.ia

## 1. FASE 3 — Borrar legacy app/api_v1/ (tras 2-3 días estables)
- El switch a src.api.app está estable desde sesión 18/05 (commit 731becc)
- Tras confirmar que no hay regresiones, borrar:
  - `app/api_v1/` entera
  - `app/main.py` (si solo se usa para esta app)
  - `tests/test_api_endpoints.py` (mockea app legacy, ya obsoleto)
- Mantener `tests/test_api_auth.py` si sigue siendo útil contra src.api.app

## 2. Recalibración del modelo Normal (sesión dedicada 3-4h)
- **Bloque C completado (24/05):** settle daemon ahora persiste outcomes
  de TODOS los análisis NBA, no solo los que generaron value_bet.
- Esperar 2-3 semanas para acumular dataset libre de sesgo de
  selector. Mínimo deseable: ~100 partidos sin sesgo + los 53 ya
  fetcheados.
- Cuando haya suficientes datos: aplicar Isotonic Regression u
  otra técnica según diagnóstico actualizado.
- **Diagnóstico hecho (sesión 2026-05-24):**
  - 127 picks NBA paper, win rate real 43.3% vs p_pred media 61.3%
  - Brier Score: 0.29 (peor que baseline 0.25)
  - ECE: 0.21 (grave — umbral problemático es 0.05)
  - Sobreconfianza no-lineal: bien calibrado en 55-60%, desbocado en 65-80%
- **Método recomendado:** Isotonic Regression (no-paramétrico,
  captura la no-linealidad). Platt Scaling no es suficiente.
- **Precaución:** 127 picks es dataset pequeño; validar con CV.

## 3. Validar dashboard end-to-end unos días
- Ahora todo funciona: ROI -7.75% correcto, filtro NBA, engine-config
- Antes de añadir features nuevas (V1-V5), usarlo unos días y ver
  si emerge algún bug nuevo o decisión a tomar

## 4. WebSocket de cuotas reales (trabajo medio, cuando vuelva el interés)
- Actualmente `/api/ws/odds` emite datos mock hardcodeados (LaLiga ficticio)
- Widget Live Odds oculto en dashboard hasta que se implemente
  (`*ngIf="false"` en dashboard.component.ts)
- Trabajo necesario:
  - Integrar OddsClient en `src/api/websockets.py`
  - Definir frecuencia de polling (cuota API limit 500/mes)
  - Cache local con TTL para evitar re-llamadas
  - Reactivar widget en dashboard.component.ts (quitar `*ngIf="false"`)

## 5. Dashboard V1-V5 (varias sesiones)
- V1: Picks pendientes con accept/reject
- V2: Histórico de picks
- V3: Métricas (ROI, drawdown, varianza)
- V4: Breakdown por mercado
- V5: Análisis A vs B (modelo A auto-track vs modelo B con tus decisiones)

## 6. Pulidos infraestructura
- **Tailscale como servicio Windows**: hoy arranca con sesión de usuario,
  no como servicio del sistema. Si Windows reinicia y queda en login screen,
  acceso remoto roto. Solución: `tailscale.exe service install` (requiere admin)
- **MagicDNS**: ✓ resuelto (sesión 18/05). Acceso vía
  http://winstake-host:4200 funciona. CORS incluye el hostname,
  ng serve corre con --disable-host-check
- **reload=False en producción**: uvicorn corre con `reload=True` en
  run_api.py. Cambiar a `reload=False` cuando se estabilice el desarrollo
  activo (evita StatReload race conditions al guardar archivos)
