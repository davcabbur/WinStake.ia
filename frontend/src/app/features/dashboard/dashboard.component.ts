import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription, forkJoin } from 'rxjs';

import { StatsCardsComponent } from './components/stats-cards/stats-cards.component';
import { HistoryTableComponent } from './components/history-table/history-table.component';
import { LiveOddsComponent } from './components/live-odds/live-odds.component';
import { ProfitChartComponent } from './components/profit-chart/profit-chart.component';

import { ApiService, DashboardStats, BetHistory, ChartData } from '../../core/services/api.service';
import { WebsocketService, OddsUpdate } from '../../core/services/websocket.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, StatsCardsComponent, HistoryTableComponent, LiveOddsComponent, ProfitChartComponent],
  template: `
    <!-- Error banner -->
    <div class="error-banner" *ngIf="loadError">
      ⚠ No se pudieron cargar los datos del dashboard. Verifica que la API esté activa.
    </div>

    <!-- Stats skeleton -->
    <div class="stats-skeleton" *ngIf="loading">
      <div class="skeleton skeleton-card" *ngFor="let _ of [1,2,3]"></div>
    </div>
    <app-stats-cards [stats]="stats" *ngIf="!loading"></app-stats-cards>

    <!-- Chart skeleton -->
    <div class="glass-card skeleton-chart-wrap" *ngIf="loading">
      <div class="skeleton skeleton-title"></div>
      <div class="skeleton" style="height:200px; border-radius:8px;"></div>
    </div>
    <app-profit-chart [chartData]="chartData" *ngIf="!loading"></app-profit-chart>

    <div class="main-grid">
      <div class="history-column">
        <!-- History skeleton -->
        <div class="glass-card" *ngIf="loading">
          <div class="skeleton skeleton-title"></div>
          <div class="skeleton skeleton-row" *ngFor="let _ of [1,2,3,4,5]"></div>
        </div>
        <app-history-table [history]="history" *ngIf="!loading"></app-history-table>
      </div>
      <div class="live-column">
        <app-live-odds [data]="liveOddsData"></app-live-odds>
      </div>
    </div>
  `,
  styles: [`
    .main-grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 32px;
    }
    .stats-skeleton {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 24px;
      margin-bottom: 32px;
    }
    .skeleton-chart-wrap {
      margin-bottom: 32px;
      padding: 24px;
    }
    @media (max-width: 1100px) {
      .main-grid { grid-template-columns: 1fr; }
    }
  `]
})
export class DashboardComponent implements OnInit, OnDestroy {
  stats: DashboardStats | null = null;
  history: BetHistory[] = [];
  chartData: ChartData | null = null;
  liveOddsData: OddsUpdate | null = null;

  loading = true;
  loadError = false;

  private wsSubscription: Subscription | null = null;

  constructor(private apiService: ApiService, private wsService: WebsocketService) {}

  ngOnInit() {
    this.loadData();
    this.setupWebsocket();
  }

  private loadData() {
    this.loading = true;
    this.loadError = false;

    forkJoin({
      stats: this.apiService.getStats(),
      history: this.apiService.getHistory(10),
      chart: this.apiService.getChartData(),
    }).subscribe({
      next: ({ stats, history, chart }) => {
        this.stats = stats;
        this.history = history.data;
        this.chartData = chart;
        this.loading = false;
      },
      error: () => {
        this.loading = false;
        this.loadError = true;
      }
    });
  }

  private setupWebsocket() {
    this.wsService.connect();
    this.wsSubscription = this.wsService.odds$.subscribe({
      next: (update) => this.liveOddsData = update
    });
  }

  ngOnDestroy() {
    this.wsSubscription?.unsubscribe();
    this.wsService.disconnect();
  }
}
