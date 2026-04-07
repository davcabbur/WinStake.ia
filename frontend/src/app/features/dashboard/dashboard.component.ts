import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

import { StatsCardsComponent } from './components/stats-cards/stats-cards.component';
import { HistoryTableComponent } from './components/history-table/history-table.component';
import { LiveOddsComponent } from './components/live-odds/live-odds.component';
import { ProfitChartComponent } from './components/profit-chart/profit-chart.component';

import { ApiService, DashboardStats, BetHistory, ChartData } from '../../core/services/api.service';
import { WebsocketService, OddsUpdate } from '../../core/services/websocket.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    StatsCardsComponent,
    HistoryTableComponent,
    LiveOddsComponent,
    ProfitChartComponent
  ],
  template: `
    <!-- Stats Top Row -->
    <app-stats-cards [stats]="stats"></app-stats-cards>

    <!-- Profit Chart -->
    <app-profit-chart [chartData]="chartData"></app-profit-chart>

    <div class="main-grid">
      <!-- Left Column: History Table -->
      <div class="history-column">
        <app-history-table [history]="history"></app-history-table>
      </div>

      <!-- Right Column: Live Odds WS -->
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

    @media (max-width: 1100px) {
      .main-grid {
        grid-template-columns: 1fr;
      }
    }
  `]
})
export class DashboardComponent implements OnInit, OnDestroy {
  stats: DashboardStats | null = null;
  history: BetHistory[] = [];
  chartData: ChartData | null = null;
  liveOddsData: OddsUpdate | null = null;

  private wsSubscription: Subscription | null = null;

  constructor(
    private apiService: ApiService,
    private wsService: WebsocketService
  ) {}

  ngOnInit() {
    this.loadData();
    this.setupWebsocket();
  }

  private loadData() {
    this.apiService.getStats().subscribe({
      next: (data) => this.stats = data,
      error: (err) => console.error('Error loading stats', err)
    });

    this.apiService.getHistory(10).subscribe({
      next: (res) => this.history = res.data,
      error: (err) => console.error('Error loading history', err)
    });

    this.apiService.getChartData().subscribe({
      next: (data) => this.chartData = data,
      error: (err) => console.error('Error loading chart data', err)
    });
  }

  private setupWebsocket() {
    this.wsService.connect();
    this.wsSubscription = this.wsService.odds$.subscribe({
      next: (update) => this.liveOddsData = update
    });
  }

  ngOnDestroy() {
    if (this.wsSubscription) {
      this.wsSubscription.unsubscribe();
    }
    this.wsService.disconnect();
  }
}
