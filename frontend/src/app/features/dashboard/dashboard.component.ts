import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';

import { DashboardStore } from './dashboard.store';
import { PageTitleComponent } from './components/page-title/page-title.component';
import { KpiRowComponent } from './components/kpi-row/kpi-row.component';
import { ProfitChartComponent } from './components/profit-chart/profit-chart.component';
import { MarketWatchComponent } from './components/market-watch/market-watch.component';
import { PicksBlotterComponent } from './components/picks-blotter/picks-blotter.component';
import { ScannerComponent } from './components/scanner/scanner.component';
import { StreakRoiComponent } from './components/streak-roi/streak-roi.component';
import { TelegramFooterComponent } from './components/telegram-footer/telegram-footer.component';

/**
 * Dashboard "Terminal Pro" (handoff §5). Orquesta los paneles sobre el grid
 * principal 1fr / 360px con 1px de línea visible. Estado desde DashboardStore.
 */
@Component({
  selector: 'app-dashboard',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    CommonModule, PageTitleComponent, KpiRowComponent, ProfitChartComponent,
    MarketWatchComponent, PicksBlotterComponent, ScannerComponent,
    StreakRoiComponent, TelegramFooterComponent,
  ],
  template: `
    <div class="err" *ngIf="store.loadError()">
      No se pudieron cargar los datos del dashboard. Verifica que la API esté activa.
    </div>

    <app-page-title></app-page-title>
    <app-kpi-row [kpis]="store.kpis()"></app-kpi-row>

    <div class="grid">
      <div class="col">
        <app-profit-chart [points]="store.chart()" [stats]="store.chartStats()"></app-profit-chart>
        <app-market-watch [rows]="store.marketWatch()" [wsConnected]="store.engineActive()"></app-market-watch>
        <app-picks-blotter [picks]="store.picks()"></app-picks-blotter>
      </div>
      <div class="col">
        <app-scanner [picks]="store.scanner()" [loading]="store.scannerLoading()" [error]="store.scannerError()"></app-scanner>
        <app-streak-roi [streak]="store.streak()" [roiBySport]="store.roiBySport()" [roiByMarket]="store.roiByMarket()"></app-streak-roi>
        <app-telegram-footer [commands]="store.botCommands"></app-telegram-footer>
      </div>
    </div>
  `,
  styles: [`
    .err {
      background: var(--ws-loss-soft);
      border-bottom: 1px solid var(--ws-loss);
      color: var(--ws-loss);
      font-family: var(--ws-font-mono);
      font-size: var(--ws-text-meta);
      padding: 10px 20px;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 360px;
      gap: 1px;
      background: var(--ws-line2);
    }
    .col { background: var(--ws-bg); display: flex; flex-direction: column; }
    .col > * { display: block; }

    @media (max-width: 1100px) {
      .grid { grid-template-columns: 1fr; }
    }
  `]
})
export class DashboardComponent implements OnInit, OnDestroy {
  readonly store = inject(DashboardStore);

  ngOnInit() {
    this.store.refresh();
    this.store.subscribeLiveOdds();
  }

  ngOnDestroy() {
    this.store.teardown();
  }
}
