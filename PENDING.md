# Pendientes - WinStake.ia

## Próxima sesión

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
