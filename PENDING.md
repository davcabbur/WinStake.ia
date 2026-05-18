# Pendientes - WinStake.ia

## Próxima sesión

### Consolidación de apps — FASE 2: switch a src.api.app
- Cambiar run_api.py para servir `src.api.app` en lugar de `app.main:app`
- `pm2 restart winstake-api`
- Verificación inmediata desde browser: dashboard carga, WebSocket
  conecta, engine-config funciona
- Si algo falla: revert run_api.py + pm2 restart (30 segundos)
- Estado actual: src.api.app tiene paridad completa (commit 17f8626)

### Tras switch exitoso — fix ROI + filtro sport
- Backend: src/api/routes.py ya tiene el nuevo /dashboard/stats
  (sport param, roi_pct calculado sobre stake). Estaba listo pero
  apuntaba a la app dormida. Tras el switch, entra en producción.
- Frontend: leer roi_pct del backend en lugar de calcular con
  (profit / totalBets). Ver stats-cards.component.ts:114
- Verificar contra BD real: roi_pct debe ser -7.75%
- Historia: añadir WHERE vb.sport = ? (default 'nba') en /dashboard/history
  para filtrar picks de LaLiga deshabilitada

### Tras switch — FASE 3: borrar legacy
- Borrar app/api_v1/ del repo
- Borrar tests obsoletos que apuntaban a app/ (test_api_auth.py,
  test_api_endpoints.py si quedaron rotos)
- Mantener tests que sigan siendo válidos

### Dashboard - discrepancia de ROI
- **Mostrado**: -34.8% (ROI Estimado en dashboard)
- **Real**: -7.75% (calculado sobre stake apostado)
- **Hipótesis**: el dashboard calcula sobre bankroll, no sobre stake
- **Investigar**:
  - Endpoint que sirve la métrica (probablemente /api/stats/overview)
  - Fórmula exacta en el código
  - Decidir si mostrar ambas métricas o solo ROI sobre stake

### Dashboard - filtrar solo NBA
- En el historial aparecen picks LaLiga (Getafe vs Mallorca)
- LaLiga está deshabilitada desde commit 11fd25b
- El dashboard debería filtrar por sport='nba' o por is_paper=1
  AND sport='nba'
- O añadir selector de sport en el frontend

## Pulidos infraestructura

### Tailscale como servicio Windows
- Hoy arranca con sesión de usuario, no como servicio del sistema
- Si Windows reinicia y queda en login screen, acceso remoto roto
- Solución: tailscale.exe service install (requiere admin)

### MagicDNS no probado
- Ya activado en admin console
- Probar http://winstake-host:4200 desde dispositivos Tailscale
- Si funciona, usar siempre el nombre en vez de la IP

## Trabajo grande (sesión dedicada)

### Recalibración del modelo Normal
- Bucket 60-70% predice 64%, gana 38% (gap -26 puntos)
- Bucket >=70% predice 79%, gana 42% (gap -37 puntos)
- Sobreconfianza sistemática en alta probabilidad
- Opciones: Platt scaling, isotonic regression, recalibración
  desde cero del modelo Normal

### Dashboard V1-V5 según plan original
- V1: Picks pendientes con accept/reject
- V2: Histórico de picks
- V3: Métricas (ROI, drawdown, varianza)
- V4: Breakdown por mercado
- V5: Análisis A vs B (modelo A auto-track vs modelo B con tus
  decisiones)
