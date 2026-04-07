import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService, BetHistory, DashboardStats, SelectionStats } from '../../core/services/api.service';

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [CommonModule],
  template: `
    <!-- ROI Summary Cards -->
    <div class="summary-grid" *ngIf="stats">
      <div class="glass-card mini-card">
        <span class="mini-label">Total Apuestas</span>
        <span class="mini-value">{{ stats.total_bets }}</span>
      </div>
      <div class="glass-card mini-card">
        <span class="mini-label">Ganadas</span>
        <span class="mini-value positive">{{ stats.won_bets }}</span>
      </div>
      <div class="glass-card mini-card">
        <span class="mini-label">Win Rate</span>
        <span class="mini-value">{{ stats.win_rate | number:'1.1-1' }}%</span>
      </div>
      <div class="glass-card mini-card">
        <span class="mini-label">Profit Total</span>
        <span class="mini-value" [class.positive]="stats.total_profit > 0" [class.negative]="stats.total_profit < 0">
          {{ stats.total_profit > 0 ? '+' : '' }}{{ stats.total_profit | number:'1.2-2' }} U
        </span>
      </div>
    </div>

    <!-- Stats by Selection -->
    <div class="glass-card breakdown-card" *ngIf="breakdown.length > 0">
      <h2>Rendimiento por Mercado</h2>
      <div class="breakdown-grid">
        <div class="breakdown-item" *ngFor="let s of breakdown">
          <div class="breakdown-header">
            <span class="breakdown-name">{{ s.selection }}</span>
            <span class="breakdown-profit" [class.positive]="s.profit > 0" [class.negative]="s.profit < 0">
              {{ s.profit > 0 ? '+' : '' }}{{ s.profit | number:'1.1-1' }} U
            </span>
          </div>
          <div class="breakdown-stats">
            <span>{{ s.wins }}/{{ s.total }} ganadas</span>
            <span>EV medio: {{ s.avg_ev | number:'1.1-1' }}%</span>
            <span>ROI: {{ s.staked > 0 ? (s.profit / s.staked * 100) : 0 | number:'1.1-1' }}%</span>
          </div>
          <div class="breakdown-bar">
            <div class="bar-fill" [style.width.%]="s.total > 0 ? (s.wins / s.total) * 100 : 0"
              [class.bar-positive]="s.profit > 0" [class.bar-negative]="s.profit <= 0">
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Full History Table -->
    <div class="glass-card">
      <div class="table-header">
        <h2>Historial Completo</h2>
        <div class="pagination-info text-secondary" *ngIf="history.length > 0">
          Mostrando {{ history.length }} registros (pagina {{ currentPage + 1 }})
        </div>
      </div>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Partido</th>
              <th>Seleccion</th>
              <th>Cuota</th>
              <th>EV (%)</th>
              <th>Confianza</th>
              <th>Stake</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let bet of history">
              <td class="text-secondary">{{ bet.run_date | date:'dd/MM/yyyy HH:mm' }}</td>
              <td class="font-medium">{{ bet.home_team }} vs {{ bet.away_team }}</td>
              <td><span class="badge badge-accent">{{ bet.selection }}</span></td>
              <td class="font-medium">{{ bet.odds | number:'1.2-2' }}</td>
              <td [class.positive]="bet.ev_percent > 5">{{ bet.ev_percent > 0 ? '+' : '' }}{{ bet.ev_percent | number:'1.1-1' }}%</td>
              <td>
                <span class="badge"
                  [class.badge-success]="bet.confidence === 'Alta'"
                  [class.badge-warning]="bet.confidence === 'Media'"
                  [class.badge-error]="bet.confidence === 'Baja'">
                  {{ bet.confidence }}
                </span>
              </td>
              <td>{{ bet.stake_units | number:'1.1-1' }} U</td>
              <td>
                <span class="badge" *ngIf="bet.bet_won !== null"
                  [class.badge-success]="bet.bet_won === 1"
                  [class.badge-error]="bet.bet_won === 0">
                  {{ bet.bet_won === 1 ? '+' + (bet.profit_units | number:'1.2-2') + ' U' : 'Perdida' }}
                </span>
                <span class="badge badge-secondary" *ngIf="bet.bet_won === null">Pendiente</span>
              </td>
            </tr>
            <tr *ngIf="history.length === 0">
              <td colspan="8" class="empty-state">No hay historial disponible</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="pagination" *ngIf="history.length > 0">
        <button class="btn-page" [disabled]="currentPage === 0" (click)="prevPage()">Anterior</button>
        <button class="btn-page" [disabled]="history.length < pageSize" (click)="nextPage()">Siguiente</button>
      </div>
    </div>
  `,
  styles: [`
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }

    .mini-card {
      padding: 16px 20px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .mini-label {
      font-size: 12px;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .mini-value {
      font-size: 24px;
      font-weight: 700;
      color: var(--text-primary);
      font-variant-numeric: tabular-nums;
    }

    .positive { color: var(--status-success-text) !important; }
    .negative { color: var(--status-error-text) !important; }

    .breakdown-card {
      margin-bottom: 24px;
    }
    .breakdown-card h2 { margin-bottom: 20px; }

    .breakdown-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 16px;
    }

    .breakdown-item {
      padding: 16px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.04);
      border-radius: 12px;
    }

    .breakdown-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }

    .breakdown-name {
      font-weight: 600;
      font-size: 14px;
      color: var(--text-primary);
    }

    .breakdown-profit {
      font-weight: 700;
      font-size: 16px;
      font-variant-numeric: tabular-nums;
    }

    .breakdown-stats {
      display: flex;
      gap: 12px;
      font-size: 12px;
      color: var(--text-secondary);
      margin-bottom: 10px;
    }

    .breakdown-bar {
      height: 4px;
      background: rgba(255, 255, 255, 0.06);
      border-radius: 2px;
      overflow: hidden;
    }

    .bar-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.5s ease;
    }
    .bar-positive { background: var(--status-success-text); }
    .bar-negative { background: var(--status-error-text); }

    .table-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }

    .table-wrapper { overflow-x: auto; }

    table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      text-align: left;
    }

    th {
      color: var(--text-secondary);
      font-size: 12px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--border-color);
      white-space: nowrap;
    }

    td {
      padding: 14px;
      font-size: 13px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      white-space: nowrap;
    }

    tr:hover td { background: rgba(255, 255, 255, 0.02); }
    .text-secondary { color: var(--text-secondary); }
    .font-medium { font-weight: 500; color: var(--text-primary); }

    .badge-accent {
      background: rgba(59, 130, 246, 0.15);
      color: var(--accent-primary);
    }

    .badge-secondary {
      background: rgba(255, 255, 255, 0.1);
      color: var(--text-secondary);
    }

    .empty-state {
      text-align: center;
      color: var(--text-secondary);
      padding: 48px !important;
    }

    .pagination {
      display: flex;
      justify-content: center;
      gap: 12px;
      margin-top: 20px;
    }

    .btn-page {
      background: var(--bg-surface-hover);
      color: var(--text-primary);
      border: 1px solid var(--border-color);
      padding: 8px 20px;
      border-radius: 8px;
      font-size: 13px;
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn-page:hover { background: rgba(59, 130, 246, 0.1); }
    .btn-page:disabled { opacity: 0.4; cursor: not-allowed; }
  `]
})
export class HistoryComponent implements OnInit {
  stats: DashboardStats | null = null;
  history: BetHistory[] = [];
  breakdown: SelectionStats[] = [];

  pageSize = 50;
  currentPage = 0;

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadStats();
    this.loadHistory();
    this.loadBreakdown();
  }

  private loadStats() {
    this.api.getStats().subscribe({
      next: (s) => this.stats = s,
      error: () => {}
    });
  }

  loadHistory() {
    this.api.getHistory(this.pageSize, this.currentPage * this.pageSize).subscribe({
      next: (res) => this.history = res.data,
      error: () => {}
    });
  }

  private loadBreakdown() {
    this.api.getStatsBySelection().subscribe({
      next: (res) => this.breakdown = res.breakdown,
      error: () => {}
    });
  }

  nextPage() {
    this.currentPage++;
    this.loadHistory();
  }

  prevPage() {
    if (this.currentPage > 0) {
      this.currentPage--;
      this.loadHistory();
    }
  }
}
