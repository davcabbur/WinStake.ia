# Pendientes - WinStake.ia

## 1. FASE 3 — Borrar legacy app/api_v1/ (tras 2-3 días estables)
- El switch a src.api.app está estable desde sesión 18/05 (commit 731becc)
- Tras confirmar que no hay regresiones, borrar:
  - `app/api_v1/` entera
  - `app/main.py` (si solo se usa para esta app)
  - `tests/test_api_endpoints.py` (mockea app legacy, ya obsoleto)
- Mantener `tests/test_api_auth.py` si sigue siendo útil contra src.api.app

## 2. Recalibración del modelo Normal (sesión dedicada 3-4h)
- Bucket 60-70% predice 64%, gana 38% (gap -26 puntos)
- Bucket >=70% predice 79%, gana 42% (gap -37 puntos)
- Sobreconfianza sistemática en alta probabilidad
- Opciones: Platt scaling, isotonic regression, recalibración
  desde cero del modelo Normal

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
- **MagicDNS**: ya activado en admin console. Probar
  http://winstake-host:4200 desde dispositivos Tailscale.
  Si funciona, usar siempre el nombre en vez de la IP
- **reload=False en producción**: uvicorn corre con `reload=True` en
  run_api.py. Cambiar a `reload=False` cuando se estabilice el desarrollo
  activo (evita StatReload race conditions al guardar archivos)
