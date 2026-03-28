import { Component, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-stats-cards',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="stats-grid">
      <div class="glass-card stat-card">
        <div class="stat-header">
          <span class="icon">📈</span>
          <h3>Beneficio Total</h3>
        </div>
        <div class="stat-value" [class.positive]="profit > 0" [class.negative]="profit < 0">
          {{ profit > 0 ? '+' : '' }}{{ profit | number:'1.2-2' }} U
        </div>
      </div>
      
      <div class="glass-card stat-card">
        <div class="stat-header">
          <span class="icon">🎯</span>
          <h3>Win Rate</h3>
        </div>
        <div class="stat-value">
          {{ winRate | number:'1.1-1' }}%
        </div>
        <div class="stat-sub">
          {{ wonBets }} / {{ totalBets }} apuestas ganadas
        </div>
      </div>
      
      <div class="glass-card stat-card">
        <div class="stat-header">
          <span class="icon">💰</span>
          <h3>ROI Estimado</h3>
        </div>
        <div class="stat-value" [class.positive]="roi > 0" [class.negative]="roi < 0">
          {{ roi > 0 ? '+' : '' }}{{ roi | number:'1.1-1' }}%
        </div>
        <div class="stat-sub">
          Basado en {{ totalBets }} apuestas
        </div>
      </div>
    </div>
  `,
  styles: [`
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 24px;
      margin-bottom: 32px;
    }
    
    .stat-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
    }
    
    .stat-header h3 {
      font-size: 14px;
      color: var(--text-secondary);
      font-weight: 500;
    }
    
    .icon {
      font-size: 20px;
      background: var(--bg-main);
      width: 40px;
      height: 40px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 12px;
      border: 1px solid var(--border-color);
    }
    
    .stat-value {
      font-size: 32px;
      font-weight: 700;
      color: var(--text-primary);
      letter-spacing: -0.02em;
    }
    
    .stat-value.positive { color: var(--status-success-text); }
    .stat-value.negative { color: var(--status-error-text); }
    
    .stat-sub {
      margin-top: 8px;
      font-size: 13px;
      color: var(--text-secondary);
    }
  `]
})
export class StatsCardsComponent implements OnChanges {
  @Input() stats: any;

  totalBets = 0;
  wonBets = 0;
  winRate = 0;
  profit = 0;
  roi = 0;

  ngOnChanges() {
    if (this.stats) {
      this.totalBets = this.stats.total_bets || 0;
      this.wonBets = this.stats.won_bets || 0;
      this.winRate = this.stats.win_rate || 0;
      this.profit = this.stats.total_profit || 0;
      // Rough ROI calculation assuming avg 1 unit staked per bet
      this.roi = this.totalBets > 0 ? (this.profit / this.totalBets) * 100 : 0;
    }
  }
}
