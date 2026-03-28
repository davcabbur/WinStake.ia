import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';

import { SidebarComponent } from '../../core/components/sidebar/sidebar.component';
import { TopbarComponent } from '../../core/components/topbar/topbar.component';
import { StatsCardsComponent } from './components/stats-cards/stats-cards.component';
import { HistoryTableComponent } from './components/history-table/history-table.component';
import { LiveOddsComponent } from './components/live-odds/live-odds.component';

import { ApiService, DashboardStats, BetHistory } from '../../core/services/api.service';
import { WebsocketService, OddsUpdate } from '../../core/services/websocket.service';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule, 
    SidebarComponent, 
    TopbarComponent, 
    StatsCardsComponent, 
    HistoryTableComponent, 
    LiveOddsComponent
  ],
  template: `
    <div class="dashboard-layout">
      <!-- Sidebar Navigation -->
      <app-sidebar></app-sidebar>
      
      <!-- Main Content Area -->
      <div class="dashboard-content">
        <app-topbar></app-topbar>
        
        <div class="content-wrapper">
          <!-- Stats Top Row -->
          <app-stats-cards [stats]="stats"></app-stats-cards>
          
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
        </div>
      </div>
    </div>
  `,
  styles: [`
    .content-wrapper {
      padding: 0 40px 40px 40px;
      max-width: 1400px;
    }
    
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

    this.apiService.getHistory().subscribe({
      next: (res) => this.history = res.data,
      error: (err) => console.error('Error loading history', err)
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
