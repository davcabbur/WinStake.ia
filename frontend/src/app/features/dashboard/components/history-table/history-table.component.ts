import { Component, Input } from '@angular/core';
import { CommonModule, DatePipe } from '@angular/common';

@Component({
  selector: 'app-history-table',
  standalone: true,
  imports: [CommonModule],
  providers: [DatePipe],
  template: `
    <div class="glass-card table-container">
      <div class="header-row">
        <h2>Historial de Apuestas</h2>
      </div>
      
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Partido</th>
              <th>Selección</th>
              <th>Cuota</th>
              <th>EV (%)</th>
              <th>Confianza</th>
              <th>Stake</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let bet of history">
              <td class="text-secondary">{{ bet.run_date | date:'dd/MM HH:mm' }}</td>
              <td class="font-medium">{{ bet.home_team }} vs {{ bet.away_team }}</td>
              <td><span class="badge badge-accent">{{ bet.selection }}</span></td>
              <td class="font-medium">{{ bet.odds | number:'1.2-2' }}</td>
              <td [class.success-text]="bet.ev_percent > 5">{{ bet.ev_percent > 0 ? '+' : '' }}{{ bet.ev_percent | number:'1.1-1' }}%</td>
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
                  {{ bet.bet_won === 1 ? '+' + (bet.profit_units | number:'1.2-2') : 'Perdida' }}
                </span>
                <span class="badge badge-secondary" *ngIf="bet.bet_won === null">
                  Pendiente
                </span>
              </td>
            </tr>
            <tr *ngIf="!history || history.length === 0">
              <td colspan="8" class="empty-state">No hay historial disponible</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .table-container {
      margin-bottom: 32px;
      overflow: hidden;
    }
    
    .header-row {
      margin-bottom: 24px;
    }
    
    .table-wrapper {
      overflow-x: auto;
    }
    
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
      padding: 12px 16px;
      border-bottom: 1px solid var(--border-color);
      white-space: nowrap;
    }
    
    td {
      padding: 16px;
      font-size: 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      white-space: nowrap;
    }
    
    tr:last-child td {
      border-bottom: none;
    }
    
    tr:hover td {
      background: rgba(255, 255, 255, 0.02);
    }
    
    .text-secondary { color: var(--text-secondary); }
    .font-medium { font-weight: 500; color: var(--text-primary); }
    .success-text { color: var(--status-success-text); }
    
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
  `]
})
export class HistoryTableComponent {
  @Input() history: any[] = [];
}
