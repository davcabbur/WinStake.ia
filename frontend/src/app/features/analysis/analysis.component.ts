import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService, ValueBet, AnalysisResult } from '../../core/services/api.service';

@Component({
  selector: 'app-analysis',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="analysis-page">
      <!-- Run Analysis Section -->
      <div class="glass-card action-card">
        <div class="action-row">
          <div>
            <h3>Motor de Analisis</h3>
            <p class="text-secondary">Ejecuta el modelo Poisson + Kelly sobre los proximos partidos de La Liga</p>
          </div>
          <button class="btn-primary" (click)="runAnalysis()" [disabled]="isRunning">
            {{ isRunning ? 'Analizando...' : 'Ejecutar Analisis' }}
          </button>
        </div>
        <div class="run-info" *ngIf="totalAnalyzed > 0">
          <span class="badge badge-accent">{{ totalAnalyzed }} partidos analizados</span>
          <span class="badge badge-success" *ngIf="valueBets.length > 0">{{ valueBets.length }} value bets detectadas</span>
          <span class="badge badge-secondary" *ngIf="valueBets.length === 0">Sin value bets</span>
        </div>
        <div class="error-msg" *ngIf="errorMsg">{{ errorMsg }}</div>
      </div>

      <!-- Live Value Bets (from engine) -->
      <div *ngIf="valueBets.length > 0">
        <h2 class="section-title">Value Bets Detectadas</h2>
        <div class="bets-grid">
          <div class="glass-card bet-card" *ngFor="let bet of valueBets">
            <div class="bet-header">
              <span class="match-name">{{ bet.match }}</span>
              <span class="badge"
                [class.badge-success]="bet.confidence === 'Alta'"
                [class.badge-warning]="bet.confidence === 'Media'"
                [class.badge-error]="bet.confidence === 'Baja'">
                {{ bet.confidence }}
              </span>
            </div>
            <div class="bet-time text-secondary">{{ bet.commence_time | date:'dd/MM/yyyy HH:mm' }}</div>

            <div class="bet-metrics">
              <div class="metric">
                <span class="metric-label">Seleccion</span>
                <span class="metric-value accent">{{ bet.selection }}</span>
              </div>
              <div class="metric">
                <span class="metric-label">Cuota</span>
                <span class="metric-value">{{ bet.odds | number:'1.2-2' }}</span>
              </div>
              <div class="metric">
                <span class="metric-label">EV</span>
                <span class="metric-value positive">+{{ bet.ev_percent | number:'1.1-1' }}%</span>
              </div>
              <div class="metric">
                <span class="metric-label">Prob. Modelo</span>
                <span class="metric-value">{{ bet.probability * 100 | number:'1.1-1' }}%</span>
              </div>
              <div class="metric">
                <span class="metric-label">Kelly</span>
                <span class="metric-value">{{ bet.kelly_half | number:'1.2-2' }}%</span>
              </div>
              <div class="metric">
                <span class="metric-label">Stake</span>
                <span class="metric-value">{{ bet.stake_units | number:'1.1-1' }} U</span>
              </div>
            </div>

            <!-- Probability bar -->
            <div class="prob-bar-container">
              <div class="prob-bar">
                <div class="prob-segment prob-implied" [style.width.%]="(1 / bet.odds) * 100"></div>
                <div class="prob-segment prob-model" [style.width.%]="bet.probability * 100"></div>
              </div>
              <div class="prob-legend">
                <span><span class="dot implied"></span> Implicita {{ (1 / bet.odds) * 100 | number:'1.0-0' }}%</span>
                <span><span class="dot model"></span> Modelo {{ bet.probability * 100 | number:'1.0-0' }}%</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent Analysis History -->
      <div *ngIf="recentResults.length > 0">
        <h2 class="section-title">Analisis Recientes</h2>
        <div class="glass-card">
          <div class="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Partido</th>
                  <th>P(1)</th>
                  <th>P(X)</th>
                  <th>P(2)</th>
                  <th>O/U 2.5</th>
                  <th>Recomendacion</th>
                  <th>Confianza</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let r of recentResults">
                  <td class="text-secondary">{{ r.run_date | date:'dd/MM HH:mm' }}</td>
                  <td class="font-medium">{{ r.home_team }} vs {{ r.away_team }}</td>
                  <td>{{ r.prob_home * 100 | number:'1.0-0' }}%</td>
                  <td>{{ r.prob_draw * 100 | number:'1.0-0' }}%</td>
                  <td>{{ r.prob_away * 100 | number:'1.0-0' }}%</td>
                  <td>
                    <span class="text-secondary">O:</span> {{ r.prob_over25 * 100 | number:'1.0-0' }}%
                    <span class="text-secondary">U:</span> {{ r.prob_under25 * 100 | number:'1.0-0' }}%
                  </td>
                  <td>
                    <span class="badge badge-accent" *ngIf="r.recommendation !== 'No apostar'">{{ r.recommendation }}</span>
                    <span class="text-secondary" *ngIf="r.recommendation === 'No apostar'">--</span>
                  </td>
                  <td>
                    <span class="badge"
                      [class.badge-success]="r.confidence === 'Alta'"
                      [class.badge-warning]="r.confidence === 'Media'"
                      [class.badge-error]="r.confidence === 'Baja'">
                      {{ r.confidence }}
                    </span>
                    <span *ngIf="!r.confidence || r.confidence === '\u2014'" class="text-secondary">--</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div class="glass-card empty-state" *ngIf="!isRunning && valueBets.length === 0 && recentResults.length === 0 && !errorMsg">
        <p>Pulsa "Ejecutar Analisis" para obtener value bets de los proximos partidos.</p>
      </div>
    </div>
  `,
  styles: [`
    .action-card { margin-bottom: 32px; }

    .action-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 24px;
    }

    .action-row p { margin-top: 4px; }

    .btn-primary {
      background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
      color: white;
      border: none;
      padding: 12px 28px;
      border-radius: 10px;
      font-weight: 600;
      font-size: 14px;
      cursor: pointer;
      transition: opacity 0.2s, transform 0.1s;
      white-space: nowrap;
    }
    .btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }
    .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

    .run-info {
      margin-top: 16px;
      display: flex;
      gap: 8px;
    }

    .error-msg {
      margin-top: 12px;
      color: var(--status-error-text);
      font-size: 13px;
    }

    .section-title {
      margin: 32px 0 16px 0;
    }

    .bets-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
      gap: 20px;
    }

    .bet-card { padding: 20px; }

    .bet-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .match-name {
      font-weight: 600;
      font-size: 15px;
      color: var(--text-primary);
    }

    .bet-time {
      font-size: 12px;
      margin-top: 4px;
    }

    .bet-metrics {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 16px;
    }

    .metric {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .metric-label {
      font-size: 11px;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .metric-value {
      font-size: 18px;
      font-weight: 700;
      color: var(--text-primary);
      font-variant-numeric: tabular-nums;
    }

    .metric-value.accent { color: var(--accent-primary); }
    .metric-value.positive { color: var(--status-success-text); }

    .prob-bar-container { margin-top: 16px; }

    .prob-bar {
      height: 6px;
      background: rgba(255, 255, 255, 0.06);
      border-radius: 3px;
      position: relative;
      overflow: hidden;
    }

    .prob-segment {
      position: absolute;
      height: 100%;
      border-radius: 3px;
      top: 0; left: 0;
    }

    .prob-implied {
      background: rgba(239, 68, 68, 0.4);
      z-index: 1;
    }

    .prob-model {
      background: var(--status-success-text);
      z-index: 2;
      opacity: 0.7;
    }

    .prob-legend {
      display: flex;
      gap: 16px;
      margin-top: 8px;
      font-size: 11px;
      color: var(--text-secondary);
    }

    .prob-legend span { display: flex; align-items: center; gap: 4px; }

    .dot {
      width: 6px; height: 6px;
      border-radius: 50%;
      display: inline-block;
    }
    .dot.implied { background: rgba(239, 68, 68, 0.6); }
    .dot.model { background: var(--status-success-text); }

    /* Table styles */
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
      padding: 48px;
      color: var(--text-secondary);
    }

    @media (max-width: 768px) {
      .action-row { flex-direction: column; align-items: flex-start; }
      .bets-grid { grid-template-columns: 1fr; }
      .bet-metrics { grid-template-columns: repeat(2, 1fr); }
    }
  `]
})
export class AnalysisComponent implements OnInit {
  valueBets: ValueBet[] = [];
  recentResults: AnalysisResult[] = [];
  totalAnalyzed = 0;
  isRunning = false;
  errorMsg = '';

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.loadRecentResults();
  }

  loadRecentResults() {
    this.api.getAnalysisResults().subscribe({
      next: (res) => this.recentResults = res.results,
      error: () => {}
    });
  }

  runAnalysis() {
    this.isRunning = true;
    this.errorMsg = '';
    this.valueBets = [];
    this.totalAnalyzed = 0;

    this.api.runAnalysis().subscribe({
      next: (res) => {
        this.valueBets = res.value_bets;
        this.totalAnalyzed = res.total_analyzed;
        this.isRunning = false;
        this.loadRecentResults();
      },
      error: (err) => {
        this.errorMsg = err.status === 404
          ? 'No se encontraron partidos proximos para analizar.'
          : 'Error al ejecutar analisis. Verifica que las API keys esten configuradas.';
        this.isRunning = false;
      }
    });
  }
}
