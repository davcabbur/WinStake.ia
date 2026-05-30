import { MarketRow, BotCommandVM } from './dashboard.models';

/**
 * ───────────────────────────────────────────────────────────────────────────
 * HANDOFF-DEVIATION — DATOS MOCK
 * ───────────────────────────────────────────────────────────────────────────
 * El backend FastAPI actual NO expone los datos que estos paneles necesitan, y
 * el handoff prohíbe refactorizar el backend (decisión del manager: "solo
 * frontend + mock marcado"). Estos seeds reproducen la fidelidad visual del
 * diseño. Sustituir por datos reales cuando existan los endpoints/WS:
 *
 *  - MARKET_WATCH_SEED → WS enriquecido /ws/live-odds con edge del modelo,
 *    cuotas previas y odds_history (sparkline). El /api/ws/odds actual sólo
 *    emite home/away/draw sin nada de eso. El store SÍ sobreescribe las cuotas
 *    1/X/2 con datos reales del WS cuando llegan (ver DashboardStore).
 *  - BOT_COMMANDS → log real del bot de Telegram (no hay endpoint).
 * ───────────────────────────────────────────────────────────────────────────
 */

export const MARKET_WATCH_SEED: MarketRow[] = [
  { id: 'rma-atm', time: "75'", live: true,  sport: 'LaLiga', match: 'Real Madrid — Atlético',  h: 1.95, d: 3.40, a: 4.20, prevH: 2.00, prevD: 3.30, prevA: 4.10, edgeSide: 'd', edgeEV: 4.2,  spark: [2.05,2.04,2.02,2.00,1.99,1.97,1.96,1.95] },
  { id: 'lal-bos', time: 'Q3',  live: true,  sport: 'NBA',    match: 'Lakers — Celtics',         h: 2.10, d: null, a: 1.78, prevH: 1.95, prevD: null, prevA: 1.90, edgeSide: 'h', edgeEV: 8.5,  spark: [1.95,1.98,2.02,2.05,2.08,2.10,2.09,2.10] },
  { id: 'ath-rso', time: '21:00', live: false, sport: 'LaLiga', match: 'Athletic — Real Sociedad', h: 2.50, d: 3.10, a: 2.80, prevH: 2.45, prevD: 3.15, prevA: 2.85, edgeSide: 'h', edgeEV: 4.2,  spark: [2.45,2.46,2.48,2.47,2.49,2.50,2.50,2.50] },
  { id: 'buc-mia', time: '19:00', live: false, sport: 'NBA',    match: 'Bucks — Heat',             h: 1.62, d: null, a: 2.35, prevH: 1.58, prevD: null, prevA: 2.40, edgeSide: 'a', edgeEV: 3.1,  spark: [2.40,2.39,2.37,2.36,2.36,2.35,2.34,2.35] },
  { id: 'gir-val', time: '22:00', live: false, sport: 'LaLiga', match: 'Girona — Valencia',        h: 1.85, d: 3.60, a: 4.10, prevH: 1.92, prevD: 3.55, prevA: 4.00, edgeSide: 'h', edgeEV: 5.8,  spark: [1.92,1.91,1.89,1.88,1.87,1.86,1.86,1.85] },
  { id: 'vil-bet', time: '21:00', live: false, sport: 'LaLiga', match: 'Villarreal — Betis',       h: 2.05, d: 3.30, a: 3.60, prevH: 2.10, prevD: 3.25, prevA: 3.55, edgeSide: 'h', edgeEV: 5.4,  spark: [2.10,2.09,2.08,2.07,2.06,2.06,2.05,2.05] },
  { id: 'sun-lal', time: '22:30', live: false, sport: 'NBA',    match: 'Suns — Lakers',            h: 1.92, d: null, a: 1.95, prevH: 1.88, prevD: null, prevA: 2.00, edgeSide: 'h', edgeEV: 4.1,  spark: [1.88,1.89,1.90,1.91,1.91,1.92,1.92,1.92] },
  { id: 'nug-thu', time: '23:00', live: false, sport: 'NBA',    match: 'Nuggets — Thunder',        h: 1.78, d: null, a: 2.15, prevH: 1.80, prevD: null, prevA: 2.12, edgeSide: null, edgeEV: null, spark: [1.80,1.80,1.79,1.79,1.78,1.78,1.78,1.78] },
];

export const BOT_COMMANDS: BotCommandVM[] = [
  { cmd: '/nba',    time: '16:38', detail: '2 picks dispatched' },
  { cmd: '/laliga', time: '16:41', detail: '2 picks dispatched' },
  { cmd: '/roi',    time: '16:30', detail: 'queried by 3 users' },
];
