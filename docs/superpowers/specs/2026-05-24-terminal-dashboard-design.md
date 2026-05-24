# WinStake.ia — Dashboard "Terminal Pro" · Implementation Design

**Date:** 2026-05-24
**Scope:** Dashboard screen only (`/` route). No other screens.
**Visual reference:** `WinStake.ia/design_handoff_dashboard_terminal/` (README.md + reference/direction-1-terminal.jsx)

---

## 1. Context

Full redesign of the Dashboard from a glassmorphism UI to a Bloomberg-style trading terminal aesthetic. The visual spec is fully defined in `design_handoff_dashboard_terminal/README.md` — this document covers only the **architectural decisions** made during the implementation brainstorm.

---

## 2. Shell Architecture

**Decision:** Dashboard bypasses the existing sidebar + topbar shell. Other routes keep the old shell untouched.

**Implementation:**

`app.routes.ts` — add `data: { layout: 'terminal' }` to the `/` route:
```ts
{ path: '', data: { layout: 'terminal' }, loadComponent: () => ... DashboardComponent }
```

`app.component.ts` — read route data via `ActivatedRoute` and switch layout:
```html
<ng-container *ngIf="isTerminalLayout; else defaultShell">
  <router-outlet></router-outlet>
</ng-container>
<ng-template #defaultShell>
  <div class="app-layout">
    <app-sidebar></app-sidebar>
    <div class="app-main">
      <app-topbar></app-topbar>
      <div class="app-content"><router-outlet></router-outlet></div>
    </div>
  </div>
</ng-template>
```

The `DashboardComponent` owns 100vw × 100vh and manages Ticker Strip, Header, grid content, and Status Line internally.

---

## 3. Tokens & Fonts

- Copy `WinStake.ia/design_handoff_dashboard_terminal/tokens.css` → `frontend/src/styles/tokens.css`
- Add `@import './tokens.css';` at top of `frontend/src/styles.css`
- Add JetBrains Mono to `index.html` alongside existing Inter import:

```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

- Remove or namespace old glassmorphism tokens (`.glass-card`, `--bg-surface`, etc.) — they are only used by non-dashboard routes so they stay but do not conflict.

---

## 4. State Management

New `DashboardStore` service using Angular 18 signals. Does NOT replace `ApiService` — it wraps it.

```ts
@Injectable({ providedIn: 'root' })
export class DashboardStore {
  readonly stats       = signal<Stats | null>(null);
  readonly profitCurve = signal<ProfitPoint[]>([]);
  readonly picks       = signal<Pick[]>([]);
  readonly period      = signal<Period>('TODO');
  // mock signals (TODO: connect when backend endpoints exist)
  readonly liveOdds    = signal<LiveMatch[]>(MOCK_LIVE_ODDS);
  readonly topPicks    = signal<TopPick[]>(MOCK_TOP_PICKS);
  readonly streak      = signal<Streak>(MOCK_STREAK);
  readonly roiBreakdown = signal<RoiBreakdown>(MOCK_ROI);

  readonly engineActive = computed(() => this.stats() !== null);

  async refresh() { /* parallel fetch of stats, profitCurve, picks */ }
}
```

---

## 5. API Mapping

Existing backend endpoints are reused with field mapping. No backend changes.

| New model | Existing endpoint | Mapping notes |
|---|---|---|
| `Stats` | `GET /api/dashboard/stats` | `bankroll = 100 + total_profit`; `bankroll_base = 100`; `open_bets/open_exposure` → 0 until endpoint adds them; `avg_ev_30d` → from history mean |
| `ProfitPoint[]` | `GET /api/dashboard/chart-data` | `chartData.cumulative_profit[i]` + `chartData.dates[i]` |
| `Pick[]` | `GET /api/dashboard/history?limit=10` | `BetHistory` → `Pick`: `run_date→timestamp`, `home+away→match`, `profit_units→profit`, `bet_won→result` |

Three new methods added to `ApiService`:
- `getTerminalStats(): Observable<Stats>`
- `getProfitCurve(): Observable<ProfitPoint[]>`
- `getTerminalPicks(limit): Observable<Pick[]>`

---

## 6. Chart Implementation

**Decision:** Pure inline SVG — no external chart library.

Matches the approach in `reference/direction-1-terminal.jsx`. The `ProfitChartComponent` computes the bicolor polyline by:
1. Calculating segment intersections with y=0
2. Rendering segments above zero in `var(--ws-win)`, below in `var(--ws-loss)`
3. Stroke width 1.6px, no fill

Viewbox `0 0 1080 280` (adjusted for Angular column width vs. full-width mockup). Axis labels in `var(--ws-font-mono)`.

---

## 7. Component Catalog

All in `frontend/src/app/features/dashboard/components/`. All standalone, OnPush, signal-based inputs where Angular 18 supports it.

Old sub-components (`stats-cards`, `history-table`, `live-odds`, `profit-chart`) are **deleted** and replaced.

| Component | Input | Data source |
|---|---|---|
| `DashboardLayoutComponent` | — | grid container only |
| `TickerStripComponent` | `tickers: TickerItem[]` | mock (static) |
| `DashboardHeaderComponent` | `engineActive: boolean` | `DashboardStore` |
| `StatusLineComponent` | `stats: Stats\|null` | `DashboardStore` |
| `KpiCardComponent` | `label, value, sub, color` | parent |
| `KpiRowComponent` | `stats: Stats\|null` | `DashboardStore` |
| `ProfitChartComponent` | `points: ProfitPoint[]` | `DashboardStore` |
| `MarketWatchComponent` | `matches: LiveMatch[]` | mock (TODO: WS) |
| `SparklineComponent` | `data: number[], color` | parent |
| `ScannerComponent` | `picks: TopPick[]` | mock |
| `PicksTableComponent` | `picks: Pick[]` | `DashboardStore` |
| `StreakComponent` | `streak: Streak` | mock |
| `RoiBreakdownComponent` | `breakdown: RoiBreakdown` | mock |
| `TelegramFooterComponent` | — | static mock |

---

## 8. Implementation Phases

### Phase 1 — Infrastructure & Frame
1. `tokens.css` → `src/styles/` + `@import` in `styles.css`
2. JetBrains Mono in `index.html`
3. Route data `layout: 'terminal'` + `AppComponent` switch
4. `DashboardLayoutComponent` (grid `1fr 360px`, gap 1px)
5. `TickerStripComponent` (static mock, CSS marquee animation)
6. `DashboardHeaderComponent` (SVG logo, F1–F5 tabs, engine dot)
7. `StatusLineComponent` (footer bar)

### Phase 2 — KPIs & Profit Chart (live data)
8. `DashboardStore` + API mapping methods in `ApiService`
9. `KpiCardComponent` + `KpiRowComponent`
10. `ProfitChartComponent` (SVG bicolor)

### Phase 3 — Market Watch & Scanner (mock)
11. `SparklineComponent`
12. `MarketWatchComponent` (8 mock matches, flash animation ready)
13. `ScannerComponent` (4 mock picks)

### Phase 4 — Right column + Picks (mock + live)
14. `PicksTableComponent` (live API)
15. `StreakComponent` (mock)
16. `RoiBreakdownComponent` (mock, diverging bullet bars)
17. `TelegramFooterComponent` (static)

### Phase 5 — QA
18. Compare against `reference/WinStake Dashboard.html`
19. Document deviations with `// HANDOFF-DEVIATION:` comments

---

## 9. Constraints (from CLAUDE.md)

- No border-radius except `50%` for dots
- No shadows, no gradients on panels
- No emoji
- No mobile/responsive work
- No changes to backend FastAPI
- No animations except: engine dot pulse, cell flash on WS update, ticker marquee
- Mono = numbers. Sans = descriptive text. No exceptions.
- Amber (`--ws-amber`) only for: active tab, EV ≥ 5%, edge marker, live clock, active period button, ALERTS badge

---

## 10. Out of Scope

- Analysis, History, Live Odds, Settings screens
- Mobile responsive layout
- Backend endpoint additions
- Real WebSocket data for Market Watch (mock only)
