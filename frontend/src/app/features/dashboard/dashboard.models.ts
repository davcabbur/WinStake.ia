/**
 * View-models del Dashboard "Terminal Pro".
 * Estos tipos son lo que consumen los componentes presentacionales (input-driven),
 * desacoplados de la forma cruda de la API.
 */

export type Tone = 'text' | 'win' | 'loss' | 'amber' | 'dim';
export type Sport = 'NBA' | 'LaLiga';
export type Confidence = 'Alta' | 'Media' | 'Baja' | string;
export type PickResult = 'Ganada' | 'Perdida' | 'Pendiente';

/** Una métrica de la fila de KPIs (handoff §7.4). */
export interface KpiVM {
  label: string;
  value: string;
  sub: string;
  tone: Tone;
}

/** Punto de la curva de beneficio (handoff §7.5). */
export interface ChartPoint {
  d: string;   // etiqueta "MM-DD"
  v: number;   // beneficio acumulado en €
}

export interface ChartStats {
  high: number;
  highDate: string;
  low: number;
  lowDate: string;
  vol: number; // desviación típica del P/L por apuesta
}

/** Fila del Picks Blotter (handoff §7.7). */
export interface PickVM {
  date: string;
  sport: Sport;
  match: string;
  selection: string;
  odds: number;
  ev: number;
  conf: Confidence;
  stake: number;
  profit: number | null;
  result: PickResult;
}

/** Card del Scanner / Top Value Bets (handoff §7.8). */
export interface ScannerPickVM {
  sport: Sport;
  time: string;
  match: string;
  selection: string;
  odds: number;
  ev: number;
  conf: Confidence;
  kelly: number;      // K½ en %
  modelProb: number;  // 0–1
  marketProb: number; // 0–1
}

/** Racha (handoff §7.9). */
export interface StreakVM {
  results: ('W' | 'L')[];
  currentRun: { type: 'W' | 'L'; length: number } | null;
  worstLoss: number;
  bestWin: number;
}

/** ROI por deporte / mercado (handoff §7.10). */
export interface RoiSportVM { sport: Sport; bets: number; wr: number; roi: number; }
export interface RoiMarketVM { name: string; bets: number; roi: number; }

/** Fila de Market Watch (handoff §7.6). */
export interface MarketRow {
  id: string;
  time: string;          // "75'", "Q3", "21:00"
  live: boolean;
  sport: Sport;
  match: string;         // "Real Madrid — Atlético"
  h: number;
  d: number | null;
  a: number;
  prevH: number | null;
  prevD: number | null;
  prevA: number | null;
  edgeSide: 'h' | 'd' | 'a' | null;
  edgeEV: number | null;
  spark: number[] | null;
}

/** Comando reciente del bot de Telegram (handoff §7.11). */
export interface BotCommandVM { cmd: string; time: string; detail: string; }
