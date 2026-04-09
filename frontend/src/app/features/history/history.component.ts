import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService, BetHistory, DashboardStats, SelectionStats } from '../../core/services/api.service';
import { LocaleCurrencyPipe } from '../../shared/pipes/locale-currency.pipe';

type SortField = 'run_date' | 'odds' | 'ev_percent' | 'stake_units' | 'profit_units';
type SortDir = 'asc' | 'desc';

@Component({
  selector: 'app-history',
  standalone: true,
  imports: [CommonModule, FormsModule, LocaleCurrencyPipe],
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
          {{ stats.total_profit | localeCurrency:2:2:true }}
        </span>
      </div>
    </div>

    <!-- Skeleton while loading -->
    <div class="summary-grid" *ngIf="!stats && !statsError">
      <div class="glass-card mini-card skeleton skeleton-card" *ngFor="let _ of [1,2,3,4]" style="height:90px"></div>
    </div>

    <!-- Stats by Selection -->
    <div class="glass-card breakdown-card" *ngIf="breakdown.length > 0">
      <h2>Rendimiento por Mercado</h2>
      <div class="breakdown-grid">
        <div class="breakdown-item" *ngFor="let s of breakdown">
          <div class="breakdown-header">
            <span class="breakdown-name">{{ s.selection }}</span>
            <span class="breakdown-profit" [class.positive]="s.profit > 0" [class.negative]="s.profit < 0">
              {{ s.profit | localeCurrency:1:1:true }}
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
        <div class="table-actions">
          <!-- Filters -->
          <select class="filter-select" [(ngModel)]="filterSelection" (change)="applyFilters()">
            <option value="">Mercado: Todos</option>
            <option *ngFor="let s of selectionOptions" [value]="s">{{ s }}</option>
          </select>
          <select class="filter-select" [(ngModel)]="filterConfidence" (change)="applyFilters()">
            <option value="">Confianza: Todas</option>
            <option value="Alta">Alta</option>
            <option value="Media">Media</option>
            <option value="Baja">Baja</option>
          </select>
          <select class="filter-select" [(ngModel)]="filterResult" (change)="applyFilters()">
            <option value="">Resultado: Todos</option>
            <option value="won">Ganadas</option>
            <option value="lost">Perdidas</option>
            <option value="pending">Pendientes</option>
          </select>
          <button class="btn-export" (click)="exportCsv()" [disabled]="filteredHistory.length === 0">
            ↓ CSV
          </button>
        </div>
      </div>

      <div class="pagination-info text-secondary" *ngIf="filteredHistory.length > 0">
        Mostrando {{ filteredHistory.length }} de {{ history.length }} registros
      </div>

      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th class="sortable" (click)="sortBy('run_date')">
                Fecha <span class="sort-icon">{{ getSortIcon('run_date') }}</span>
              </th>
              <th>Partido</th>
              <th>Seleccion</th>
              <th class="sortable" (click)="sortBy('odds')">
                Cuota <span class="sort-icon">{{ getSortIcon('odds') }}</span>
              </th>
              <th class="sortable" (click)="sortBy('ev_percent')">
                EV (%) <span class="sort-icon">{{ getSortIcon('ev_percent') }}</span>
              </th>
              <th>Confianza</th>
              <th class="sortable" (click)="sortBy('stake_units')">
                Stake <span class="sort-icon">{{ getSortIcon('stake_units') }}</span>
              </th>
              <th class="sortable" (click)="sortBy('profit_units')">
                Resultado <span class="sort-icon">{{ getSortIcon('profit_units') }}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let bet of filteredHistory">
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
              <td>{{ bet.stake_units | localeCurrency:1:1 }}</td>
              <td>
                <span class="badge" *ngIf="bet.bet_won !== null"
                  [class.badge-success]="bet.bet_won === 1"
                  [class.badge-error]="bet.bet_won === 0">
                  {{ bet.bet_won === 1 ? (bet.profit_units | localeCurrency:2:2:true) : 'Perdida' }}
                </span>
                <span class="badge badge-secondary" *ngIf="bet.bet_won === null">Pendiente</span>
              </td>
            </tr>
            <tr *ngIf="filteredHistory.length === 0">
              <td colspan="8" class="empty-state">No hay registros con los filtros actuales</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <div class="pagination" *ngIf="history.length > 0">
        <button class="btn-page" [disabled]="currentPage === 0" (click)="prevPage()">Anterior</button>
        <span class="page-info text-secondary">Pág. {{ currentPage + 1 }}</span>
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
    .mini-card { padding: 16px 20px; display: flex; flex-direction: column; gap: 8px; }
    .mini-label { font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }
    .mini-value { font-size: 24px; font-weight: 700; color: var(--text-primary); font-variant-numeric: tabular-nums; }
    .positive { color: var(--status-success-text) !important; }
    .negative { color: var(--status-error-text) !important; }

    .breakdown-card { margin-bottom: 24px; }
    .breakdown-card h2 { margin-bottom: 20px; }
    .breakdown-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
    .breakdown-item { padding: 16px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04); border-radius: 12px; }
    .breakdown-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .breakdown-name { font-weight: 600; font-size: 14px; color: var(--text-primary); }
    .breakdown-profit { font-weight: 700; font-size: 16px; font-variant-numeric: tabular-nums; }
    .breakdown-stats { display: flex; gap: 12px; font-size: 12px; color: var(--text-secondary); margin-bottom: 10px; }
    .breakdown-bar { height: 4px; background: rgba(255,255,255,0.06); border-radius: 2px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 2px; transition: width 0.5s ease; }
    .bar-positive { background: var(--status-success-text); }
    .bar-negative { background: var(--status-error-text); }

    .table-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
    .table-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .pagination-info { font-size: 12px; margin-bottom: 12px; }

    .filter-select {
      background: var(--bg-main);
      border: 1px solid var(--border-color);
      color: var(--text-secondary);
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 12px;
      cursor: pointer;
    }
    .filter-select:focus { outline: none; border-color: var(--accent-primary); }

    .btn-export {
      background: rgba(59,130,246,0.1);
      border: 1px solid rgba(59,130,246,0.2);
      color: var(--accent-primary);
      border-radius: 8px;
      padding: 6px 14px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    .btn-export:hover { background: rgba(59,130,246,0.2); }
    .btn-export:disabled { opacity: 0.4; cursor: not-allowed; }

    .table-wrapper { overflow-x: auto; }
    table { width: 100%; border-collapse: separate; border-spacing: 0; text-align: left; }
    th { color: var(--text-secondary); font-size: 12px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; padding: 12px 14px; border-bottom: 1px solid var(--border-color); white-space: nowrap; }
    td { padding: 14px; font-size: 13px; border-bottom: 1px solid rgba(255,255,255,0.04); white-space: nowrap; }
    tr:hover td { background: rgba(255,255,255,0.02); }

    .sortable { cursor: pointer; user-select: none; }
    .sortable:hover { color: var(--text-primary); }
    .sort-icon { font-size: 10px; margin-left: 4px; }

    .text-secondary { color: var(--text-secondary); }
    .font-medium { font-weight: 500; color: var(--text-primary); }
    .badge-accent { background: rgba(59,130,246,0.15); color: var(--accent-primary); }
    .badge-secondary { background: rgba(255,255,255,0.1); color: var(--text-secondary); }
    .empty-state { text-align: center; color: var(--text-secondary); padding: 48px !important; }

    .pagination { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 20px; }
    .page-info { font-size: 13px; }
    .btn-page { background: var(--bg-surface-hover); color: var(--text-primary); border: 1px solid var(--border-color); padding: 8px 20px; border-radius: 8px; font-size: 13px; cursor: pointer; transition: background 0.2s; }
    .btn-page:hover { background: rgba(59,130,246,0.1); }
    .btn-page:disabled { opacity: 0.4; cursor: not-allowed; }
  `]
})
export class HistoryComponent implements OnInit {
  stats: DashboardStats | null = null;
  statsError = false;
  history: BetHistory[] = [];
  filteredHistory: BetHistory[] = [];
  breakdown: SelectionStats[] = [];
  selectionOptions: string[] = [];

  pageSize = 50;
  currentPage = 0;

  filterSelection = '';
  filterConfidence = '';
  filterResult = '';
  sortField: SortField = 'run_date';
  sortDir: SortDir = 'desc';

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.getStats().subscribe({ next: (s) => this.stats = s, error: () => this.statsError = true });
    this.loadHistory();
    this.api.getStatsBySelection().subscribe({ next: (res) => this.breakdown = res.breakdown, error: () => {} });
  }

  loadHistory() {
    this.api.getHistory(this.pageSize, this.currentPage * this.pageSize).subscribe({
      next: (res) => {
        this.history = res.data;
        this.selectionOptions = [...new Set(res.data.map(b => b.selection))].sort();
        this.applyFilters();
      },
      error: () => {}
    });
  }

  applyFilters() {
    let result = [...this.history];

    if (this.filterSelection) result = result.filter(b => b.selection === this.filterSelection);
    if (this.filterConfidence) result = result.filter(b => b.confidence === this.filterConfidence);
    if (this.filterResult === 'won') result = result.filter(b => b.bet_won === 1);
    else if (this.filterResult === 'lost') result = result.filter(b => b.bet_won === 0);
    else if (this.filterResult === 'pending') result = result.filter(b => b.bet_won === null);

    result.sort((a, b) => {
      const aVal = (a as any)[this.sortField] ?? 0;
      const bVal = (b as any)[this.sortField] ?? 0;
      const cmp = aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
      return this.sortDir === 'asc' ? cmp : -cmp;
    });

    this.filteredHistory = result;
  }

  sortBy(field: SortField) {
    if (this.sortField === field) {
      this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortField = field;
      this.sortDir = 'desc';
    }
    this.applyFilters();
  }

  getSortIcon(field: SortField): string {
    if (this.sortField !== field) return '⇅';
    return this.sortDir === 'asc' ? '↑' : '↓';
  }

  exportCsv() {
    const headers = ['Fecha', 'Partido', 'Seleccion', 'Cuota', 'EV%', 'Confianza', 'Stake', 'Resultado', 'Profit'];
    const rows = this.filteredHistory.map(b => [
      b.run_date,
      `"${b.home_team} vs ${b.away_team}"`,
      b.selection,
      b.odds,
      b.ev_percent,
      b.confidence,
      b.stake_units,
      b.bet_won === 1 ? 'Ganada' : b.bet_won === 0 ? 'Perdida' : 'Pendiente',
      b.profit_units ?? '',
    ]);
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `historial_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  nextPage() { this.currentPage++; this.loadHistory(); }
  prevPage() { if (this.currentPage > 0) { this.currentPage--; this.loadHistory(); } }
}
