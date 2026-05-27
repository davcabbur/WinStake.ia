# Pendientes - WinStake.ia

## 1. Recalibración del modelo Normal (sesión dedicada 3-4h)
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

## 2. Validar dashboard end-to-end unos días
- Ahora todo funciona: ROI -7.75% correcto, filtro NBA, engine-config
- Antes de añadir features nuevas (V1-V5), usarlo unos días y ver
  si emerge algún bug nuevo o decisión a tomar

## 3. WebSocket de cuotas reales (trabajo medio, cuando vuelva el interés)
- Actualmente `/api/ws/odds` emite datos mock hardcodeados (LaLiga ficticio)
- Widget Live Odds oculto en dashboard hasta que se implemente
  (`*ngIf="false"` en dashboard.component.ts)
- Trabajo necesario:
  - Integrar OddsClient en `src/api/websockets.py`
  - Definir frecuencia de polling (cuota API limit 500/mes)
  - Cache local con TTL para evitar re-llamadas
  - Reactivar widget en dashboard.component.ts (quitar `*ngIf="false"`)

## 4. Dashboard V1-V5 (varias sesiones)
- V1: Picks pendientes con accept/reject
- V2: Histórico de picks
- V3: Métricas (ROI, drawdown, varianza)
- V4: Breakdown por mercado
- V5: Análisis A vs B (modelo A auto-track vs modelo B con tus decisiones)

## 5. Pulidos infraestructura
- **MagicDNS**: ✓ resuelto (sesión 18/05). Acceso vía
  http://winstake-host:4200 funciona. CORS incluye el hostname,
  ng serve corre con --disable-host-check
- **Tailscale**: ✓ resuelto (24/05). Servicio `Automatic`, arranca con
  Windows sin necesidad de login de usuario. `winstake-host` + `iphone-15`
  visibles en tailnet.
- **reload=False**: ✓ resuelto (24/05). uvicorn corre sin watcher de
  ficheros. PM2 gestiona reinicios vía autorestart.

## Trabajo grande / sesión dedicada

### Player Props NBA (objetivo 2-3 meses, post-recalibración)

Sistema separado para mercados de jugador individual: puntos,
rebotes, asistencias, triples por jugador.

Pre-requisitos antes de empezar:
1. Modelo Normal recalibrado y validado (ROI break-even o positivo)
2. Dataset NBA acumulado de toda una temporada
3. Automatización de análisis funcionando

Componentes nuevos necesarios:
- Pipeline de datos: nba_api PlayerGameLog, BoxScore avanzado
- Modelo de regresión por jugador (no reutiliza el Normal)
- Tabla player_predictions desacoplada
- Detección de lesiones/lineups en tiempo real
- Variables: factor cancha, matchup defensivo, descanso,
  back-to-back, minutos esperados

Inspiración del usuario: "en un Spurs-OKC analizar últimos
partidos de Wembanyama, estado físico, factor cancha, y ver qué
picks son mejores (puntos, rebotes, triples, asistencias)".

Estimación: proyecto de 2-3 sesiones de día completo cada una.
NO empezar hasta cumplir pre-requisitos.

---

## Histórico de hitos completados
- 17/05: FIX 2 — nba_resolver persiste pnl_units + dedup NBA picks
- 18/05: FASE 2 — switch a src.api.app + fix ROI dashboard
- 18-20/05: Chart curva beneficio + CORS + MagicDNS
- 24/05: Bloque C — settle daemon persiste outcomes de TODOS los análisis NBA (sin sesgo de selector)
- 24/05: FASE 3 — eliminado app/ legacy y tests asociados
- 24/05: Tailscale — confirmado como servicio Automatic, acceso remoto garantizado
- 24/05: reload=False — uvicorn en modo producción, sin StatReload watcher

---

## Bugs conocidos

### winstake-settle estuvo caído ~21h (26/05)

El 26/05 el daemon settle no hizo ticks entre las 00:20 y las 21:50
aproximadamente, dejando picks pendientes durante todo el día.

PM2 está configurado con autorestart=true, así que un downtime de
21h sugiere uno de:
- PM2 falló al rearrancar tras un crash silencioso
- unstable_restarts se disparó y PM2 dejó de reintentar
- Algún reinicio de Windows sin levantar PM2

Diagnóstico pendiente. Cuando se aborde, revisar:
- pm2 logs winstake-settle (logs históricos con fechas)
- pm2 info winstake-settle (restart_time, unstable_restarts)
- Event Viewer Windows (apagados/reinicios entre las 00:20 y 21:50 del 26/05)
- Logs PM2: ~/.pm2/logs/winstake-settle-*.log

Prioridad: media. No es bloqueante pero deja picks pendientes ante
cualquier downtime largo del daemon.
