import { Injectable, computed, inject, signal } from '@angular/core';
import { Subscription, forkJoin } from 'rxjs';

import {
  ApiService, BetHistory, ChartData, DashboardStats, EngineConfig,
  SelectionStats, ValueBet,
} from '../../core/services/api.service';
import { WebsocketService, LiveOddMatch } from '../../core/services/websocket.service';
import { MARKET_WATCH_SEED, BOT_COMMANDS } from './dashboard.mock';
import {
  KpiVM, ChartPoint, ChartStats, PickVM, ScannerPickVM, StreakVM,
  RoiSportVM, RoiMarketVM, MarketRow, BotCommandVM, Sport,
} from './dashboard.models';

const BASE_FALLBACK = 100;
const HISTORY_FETCH = 200;   // suficiente para derivar open bets / racha / avg EV
const BLOTTER_LIMIT = 10;

/**
 * Store del Dashboard (handoff §10). Un único servicio que consume la API por
 * deporte (NBA, decisión del manager) y expone signals para los componentes
 * presentacionales. Deriva en cliente lo que el backend no da directamente
 * (bankroll, open bets, AVG EV, racha) y siembra con mock lo que no existe.
 */
@Injectable({ providedIn: 'root' })
export class DashboardStore {
  private readonly api = inject(ApiService);
  private readonly ws = inject(WebsocketService);

  // ── Estado crudo ──────────────────────────────────────────────
  private readonly stats = signal<DashboardStats | null>(null);
  private readonly config = signal<EngineConfig | null>(null);
  private readonly rawHistory = signal<BetHistory[]>([]);
  private readonly selectionBreakdown = signal<SelectionStats[]>([]);

  // ── Estado expuesto ───────────────────────────────────────────
  readonly loading = signal(true);
  readonly loadError = signal(false);

  readonly chart = signal<ChartPoint[]>([]);
  readonly chartStats = signal<ChartStats | null>(null);

  readonly scanner = signal<ScannerPickVM[]>([]);
  readonly scannerLoading = signal(false);
  readonly scannerError = signal(false);

  readonly marketWatch = signal<MarketRow[]>(MARKET_WATCH_SEED);
  readonly botCommands: BotCommandVM[] = BOT_COMMANDS;

  readonly engineActive = this.ws.connected;

  private wsSub: Subscription | null = null;

  // ── Derivados ─────────────────────────────────────────────────

  readonly bankrollBase = computed(() => this.config()?.bankroll_base ?? BASE_FALLBACK);

  readonly bankroll = computed(() => this.bankrollBase() + (this.stats()?.total_profit ?? 0));

  readonly openBets = computed(() => this.rawHistory().filter(b => b.bet_won === null).length);

  readonly openExposure = computed(() =>
    this.rawHistory().filter(b => b.bet_won === null).reduce((s, b) => s + (b.stake_units ?? 0), 0));

  readonly avgEv = computed(() => {
    const h = this.rawHistory();
    if (!h.length) return 0;
    return h.reduce((s, b) => s + (b.ev_percent ?? 0), 0) / h.length;
  });

  readonly kpis = computed<KpiVM[]>(() => {
    const s = this.stats();
    const profit = s?.total_profit ?? 0;
    const roi = s?.roi_pct ?? 0;
    const wr = s?.win_rate ?? 0;
    const total = s?.total_bets ?? 0;
    const won = s?.won_bets ?? 0;
    const ev = this.avgEv();
    return [
      { label: 'BANKROLL',  value: fmtEur(this.bankroll()),       sub: `BASE ${fmtEur(this.bankrollBase())}`, tone: 'text' },
      { label: 'P/L TOTAL', value: fmtEur(profit, true),          sub: `${total} bets`,                       tone: profit >= 0 ? 'win' : 'loss' },
      { label: 'ROI',       value: fmtPct(roi),                   sub: 'vs +3% target',                       tone: roi >= 0 ? 'win' : 'loss' },
      { label: 'WIN RATE',  value: `${wr.toFixed(1)}%`,           sub: `${won}/${total} won`,                 tone: 'amber' },
      { label: 'AVG EV',    value: fmtPct(ev),                    sub: `Últimos ${this.rawHistory().length}`, tone: ev >= 0 ? 'win' : 'loss' },
      { label: 'OPEN BETS', value: String(this.openBets()),       sub: `${fmtEur(this.openExposure())} exposed`, tone: 'text' },
    ];
  });

  readonly picks = computed<PickVM[]>(() =>
    this.rawHistory().slice(0, BLOTTER_LIMIT).map(toPickVM));

  readonly streak = computed<StreakVM>(() => buildStreak(this.rawHistory()));

  readonly roiBySport = computed<RoiSportVM[]>(() => {
    const s = this.stats();
    if (!s) return [];
    // Sólo NBA tiene datos reales (decisión: NBA por ahora).
    return [{ sport: 'NBA', bets: s.total_bets, wr: s.win_rate, roi: s.roi_pct }];
  });

  readonly roiByMarket = computed<RoiMarketVM[]>(() =>
    this.selectionBreakdown().map(b => ({
      name: b.selection,
      bets: b.total,
      roi: b.staked > 0 ? (b.profit / b.staked) * 100 : 0,
    })));

  // ── Acciones ──────────────────────────────────────────────────

  /** Carga el núcleo del dashboard (datos reales NBA). */
  refresh(): void {
    this.loading.set(true);
    this.loadError.set(false);

    forkJoin({
      stats: this.api.getStats(),
      config: this.api.getEngineConfig(),
      history: this.api.getHistory(HISTORY_FETCH),
      chart: this.api.getChartData(),
      breakdown: this.api.getStatsBySelection(),
    }).subscribe({
      next: ({ stats, config, history, chart, breakdown }) => {
        this.stats.set(stats);
        this.config.set(config);
        this.rawHistory.set(history.data ?? []);
        this.selectionBreakdown.set(breakdown.breakdown ?? []);
        this.applyChart(chart);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.loadError.set(true);
      },
    });

    this.loadScanner();
  }

  /** Top Value Bets — corre el análisis en vivo (puede ser lento o fallar). */
  loadScanner(): void {
    this.scannerLoading.set(true);
    this.scannerError.set(false);
    this.api.runAnalysis().subscribe({
      next: (res) => {
        const bets = [...(res.value_bets ?? [])].sort((a, b) => b.ev_percent - a.ev_percent).slice(0, 4);
        this.scanner.set(bets.map(toScannerVM));
        this.scannerLoading.set(false);
      },
      error: () => {
        this.scannerLoading.set(false);
        this.scannerError.set(true);
      },
    });
  }

  /** Suscribe al WS de cuotas y sobreescribe los precios reales sobre el seed. */
  subscribeLiveOdds(): void {
    this.ws.connect();
    this.wsSub = this.ws.odds$.subscribe(update => this.applyWsOdds(update.matches ?? []));
  }

  teardown(): void {
    this.wsSub?.unsubscribe();
    this.wsSub = null;
    this.ws.disconnect();
  }

  // ── Internos ──────────────────────────────────────────────────

  private applyChart(chart: ChartData): void {
    const dates = chart?.dates ?? [];
    const cum = chart?.cumulative_profit ?? [];
    const profits = chart?.profits ?? [];

    this.chart.set(dates.map((d, i) => ({ d: shortDate(d), v: cum[i] ?? 0 })));

    if (!cum.length) { this.chartStats.set(null); return; }
    let hi = cum[0], lo = cum[0], hiIdx = 0, loIdx = 0;
    cum.forEach((v, i) => {
      if (v > hi) { hi = v; hiIdx = i; }
      if (v < lo) { lo = v; loIdx = i; }
    });
    this.chartStats.set({
      high: hi, highDate: shortDate(dates[hiIdx] ?? ''),
      low: lo,  lowDate: shortDate(dates[loIdx] ?? ''),
      vol: stddev(profits),
    });
  }

  /**
   * HANDOFF-DEVIATION: el WS sólo trae home/away/draw. Sobreescribimos las
   * cuotas 1/X/2 reales sobre las filas del seed que casen por nombre de equipo,
   * conservando edge/sparkline del mock (el modelo no viaja por el WS aún).
   */
  private applyWsOdds(matches: LiveOddMatch[]): void {
    if (!matches.length) return;
    const rows = this.marketWatch().map(r => ({ ...r }));
    let touched = false;
    for (const m of matches) {
      const row = rows.find(r => rowMatchesTeams(r, m.home, m.away));
      if (!row) continue;
      touched = true;
      row.prevH = row.h; row.prevD = row.d; row.prevA = row.a;
      row.h = m.home_odd;
      row.d = m.draw_odd && m.draw_odd > 0 ? m.draw_odd : null;
      row.a = m.away_odd;
    }
    if (touched) this.marketWatch.set(rows);
  }
}

// ── Helpers de formato y derivación ─────────────────────────────

function fmtEur(v: number, sign = false): string {
  const s = v.toFixed(2).replace('.', ',') + ' €';
  return sign && v > 0 ? '+' + s : s;
}
function fmtPct(v: number, sign = true): string {
  const s = v.toFixed(1) + '%';
  return sign && v > 0 ? '+' + s : s;
}

function shortDate(d: string): string {
  if (!d) return '';
  // "2026-05-24" → "05-24"; deja intactas etiquetas ya cortas.
  return d.length >= 10 && d[4] === '-' ? d.substring(5, 10) : d;
}

function stddev(values: number[]): number {
  if (values.length < 2) return 0;
  const mean = values.reduce((s, v) => s + v, 0) / values.length;
  const variance = values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length;
  return Math.sqrt(variance);
}

function toPickVM(b: BetHistory): PickVM {
  const result = b.bet_won === 1 ? 'Ganada' : b.bet_won === 0 ? 'Perdida' : 'Pendiente';
  return {
    date: fmtPickDate(b.run_date),
    sport: 'NBA', // historial consultado por deporte = NBA
    match: `${b.home_team} — ${b.away_team}`,
    selection: b.selection,
    odds: b.odds,
    ev: b.ev_percent,
    conf: b.confidence,
    stake: b.stake_units,
    profit: b.bet_won === null ? null : (b.profit_units ?? 0),
    result,
  };
}

function toScannerVM(v: ValueBet): ScannerPickVM {
  return {
    sport: 'NBA',
    time: fmtClock(v.commence_time),
    match: v.match.replace(' vs ', ' — '),
    selection: v.selection,
    odds: v.odds,
    ev: v.ev_percent,
    conf: v.confidence,
    // kelly_half del backend ya viene en %; si llegara como fracción (<1) se asume %.
    kelly: v.kelly_half,
    modelProb: v.probability,
    marketProb: v.odds > 0 ? 1 / v.odds : 0,
  };
}

function buildStreak(history: BetHistory[]): StreakVM {
  const settled = history
    .filter(b => b.bet_won === 0 || b.bet_won === 1)
    .map<'W' | 'L'>(b => (b.bet_won === 1 ? 'W' : 'L'));

  const results = settled.slice(0, 14);

  let currentRun: StreakVM['currentRun'] = null;
  if (settled.length) {
    const type = settled[0];
    let len = 0;
    for (const r of settled) { if (r === type) len++; else break; }
    currentRun = { type, length: len };
  }

  return {
    results,
    currentRun,
    worstLoss: longestRun(settled, 'L'),
    bestWin: longestRun(settled, 'W'),
  };
}

function longestRun(seq: ('W' | 'L')[], target: 'W' | 'L'): number {
  let best = 0, cur = 0;
  for (const r of seq) {
    if (r === target) { cur++; best = Math.max(best, cur); } else cur = 0;
  }
  return best;
}

function fmtPickDate(iso: string): string {
  const dt = new Date(iso);
  if (isNaN(dt.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(dt.getDate())}/${p(dt.getMonth() + 1)} ${p(dt.getHours())}:${p(dt.getMinutes())}`;
}

function fmtClock(iso: string): string {
  const dt = new Date(iso);
  if (isNaN(dt.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(dt.getHours())}:${p(dt.getMinutes())}`;
}

function rowMatchesTeams(row: MarketRow, home: string, away: string): boolean {
  const hay = row.match.toLowerCase();
  const norm = (s: string) => (s || '').toLowerCase().split(/\s+/)[0];
  return hay.includes(norm(home)) || hay.includes(norm(away));
}
