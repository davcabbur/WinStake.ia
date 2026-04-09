import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ApiService, EngineConfig } from '../../core/services/api.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="settings-grid">

      <!-- API Status -->
      <div class="glass-card">
        <h2>Estado del Sistema</h2>
        <div class="status-list">
          <div class="status-item">
            <span>API Backend</span>
            <span class="badge" [class.badge-success]="apiStatus === 'ok'" [class.badge-error]="apiStatus === 'error'">
              {{ apiStatus === 'ok' ? 'Online' : apiStatus === 'checking' ? 'Verificando...' : 'Offline' }}
            </span>
          </div>
          <div class="status-item">
            <span>WebSocket (Live Odds)</span>
            <span class="badge badge-secondary">Disponible</span>
          </div>
          <div class="status-item">
            <span>Base de Datos</span>
            <span class="badge badge-success">SQLite</span>
          </div>
        </div>
      </div>

      <!-- Engine Parameters (editable) -->
      <div class="glass-card">
        <div class="card-header">
          <h2>Parametros del Motor</h2>
          <div class="header-actions">
            <span class="save-feedback positive" *ngIf="saveStatus === 'ok'">✓ Guardado</span>
            <span class="save-feedback negative" *ngIf="saveStatus === 'error'">Error al guardar</span>
            <button class="btn-save" (click)="saveConfig()" [disabled]="saving || !config">
              {{ saving ? 'Guardando...' : 'Guardar cambios' }}
            </button>
          </div>
        </div>

        <!-- Skeleton while loading -->
        <div *ngIf="!config && !loadError">
          <div class="skeleton skeleton-row" *ngFor="let _ of [1,2,3,4,5,6]"></div>
        </div>

        <div class="error-banner" *ngIf="loadError">
          No se pudo cargar la configuración del motor. Verifica que la API esté activa.
        </div>

        <div class="params-list" *ngIf="config">
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Modelo</span>
              <span class="param-desc text-secondary">Distribución de Poisson para probabilidades</span>
            </div>
            <span class="param-value">Poisson</span>
          </div>

          <div class="param-item">
            <div class="param-info">
              <span class="param-name">EV Mínimo</span>
              <span class="param-desc text-secondary">Umbral para considerar value bet (%)</span>
            </div>
            <div class="param-input-wrap">
              <input class="param-input" type="number" step="0.5" min="0" max="20"
                [(ngModel)]="config.ev_min" />
              <span class="param-unit">%</span>
            </div>
          </div>

          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Kelly</span>
              <span class="param-desc text-secondary">Fracción Kelly para sizing (0.5 = half-Kelly)</span>
            </div>
            <div class="param-input-wrap">
              <input class="param-input" type="number" step="0.05" min="0.1" max="1"
                [(ngModel)]="config.kelly_fraction" />
              <span class="param-unit">×</span>
            </div>
          </div>

          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Kelly Cap</span>
              <span class="param-desc text-secondary">Máximo % del bankroll por apuesta</span>
            </div>
            <div class="param-input-wrap">
              <input class="param-input" type="number" step="0.01" min="0.05" max="0.5"
                [(ngModel)]="config.kelly_cap" />
              <span class="param-unit">×</span>
            </div>
          </div>

          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Ventaja Local</span>
              <span class="param-desc text-secondary">Factor multiplicador para equipo local</span>
            </div>
            <div class="param-input-wrap">
              <input class="param-input" type="number" step="0.01" min="1" max="2"
                [(ngModel)]="config.home_advantage" />
              <span class="param-unit">×</span>
            </div>
          </div>

          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Peso xG</span>
              <span class="param-desc text-secondary">Peso de Expected Goals vs goles reales (0–1)</span>
            </div>
            <div class="param-input-wrap">
              <input class="param-input" type="number" step="0.05" min="0" max="1"
                [(ngModel)]="config.xg_weight" />
              <span class="param-unit">×</span>
            </div>
          </div>

          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Bankroll Base</span>
              <span class="param-desc text-secondary">Unidades iniciales de referencia</span>
            </div>
            <div class="param-input-wrap">
              <input class="param-input" type="number" step="10" min="10" max="10000"
                [(ngModel)]="config.bankroll_base" />
              <span class="param-unit">u.</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Markets Covered -->
      <div class="glass-card">
        <h2>Mercados Cubiertos</h2>
        <div class="markets-list">
          <div class="market-badge">1X2 (Home/Draw/Away)</div>
          <div class="market-badge">Over/Under 2.5</div>
          <div class="market-badge">BTTS (Ambos Marcan)</div>
          <div class="market-badge">Resultado Exacto</div>
          <div class="market-badge">Handicap Asiatico</div>
        </div>
      </div>

      <!-- Data Sources -->
      <div class="glass-card">
        <h2>Fuentes de Datos</h2>
        <div class="params-list">
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">The Odds API</span>
              <span class="param-desc text-secondary">Cuotas en tiempo real de multiples casas</span>
            </div>
            <span class="badge badge-success">Activa</span>
          </div>
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">API-Football</span>
              <span class="param-desc text-secondary">Estadisticas, clasificacion, xG</span>
            </div>
            <span class="badge badge-success">Activa</span>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .settings-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 24px;
    }

    h2 { margin-bottom: 20px; }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .save-feedback {
      font-size: 13px;
      font-weight: 500;
    }
    .save-feedback.positive { color: var(--status-success-text); }
    .save-feedback.negative { color: var(--status-error-text); }

    .btn-save {
      background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
      color: white;
      border: none;
      padding: 8px 18px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .btn-save:hover { opacity: 0.85; }
    .btn-save:disabled { opacity: 0.4; cursor: not-allowed; }

    .status-list, .params-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .status-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      font-size: 14px;
      color: var(--text-primary);
    }
    .status-item:last-child { border-bottom: none; }

    .param-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    }
    .param-item:last-child { border-bottom: none; }

    .param-info {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .param-name {
      font-size: 14px;
      font-weight: 500;
      color: var(--text-primary);
    }
    .param-desc { font-size: 12px; }
    .text-secondary { color: var(--text-secondary); }

    .param-value {
      font-size: 14px;
      font-weight: 600;
      color: var(--accent-primary);
      font-variant-numeric: tabular-nums;
    }

    .param-input-wrap {
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .param-input {
      width: 80px;
      background: var(--bg-main);
      border: 1px solid var(--border-color);
      color: var(--text-primary);
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 14px;
      font-weight: 600;
      font-variant-numeric: tabular-nums;
      text-align: right;
      transition: border-color 0.2s;
    }
    .param-input:focus {
      outline: none;
      border-color: var(--accent-primary);
    }

    .param-unit {
      font-size: 13px;
      color: var(--text-secondary);
      width: 16px;
    }

    .badge-secondary {
      background: rgba(255, 255, 255, 0.1);
      color: var(--text-secondary);
    }

    .markets-list {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }

    .market-badge {
      background: rgba(59, 130, 246, 0.1);
      color: var(--accent-primary);
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 500;
      border: 1px solid rgba(59, 130, 246, 0.2);
    }

    @media (max-width: 768px) {
      .settings-grid { grid-template-columns: 1fr; }
      .card-header { flex-direction: column; align-items: flex-start; gap: 12px; }
    }
  `]
})
export class SettingsComponent implements OnInit {
  apiStatus: 'checking' | 'ok' | 'error' = 'checking';
  config: EngineConfig | null = null;
  loadError = false;
  saving = false;
  saveStatus: 'idle' | 'ok' | 'error' = 'idle';

  constructor(private http: HttpClient, private api: ApiService) {}

  ngOnInit() {
    this.http.get<any>('http://localhost:8000/health').subscribe({
      next: () => this.apiStatus = 'ok',
      error: () => this.apiStatus = 'error'
    });

    this.api.getEngineConfig().subscribe({
      next: (cfg) => this.config = cfg,
      error: () => this.loadError = true
    });
  }

  saveConfig() {
    if (!this.config) return;
    this.saving = true;
    this.saveStatus = 'idle';

    this.api.updateEngineConfig(this.config).subscribe({
      next: (updated) => {
        this.config = updated;
        this.saving = false;
        this.saveStatus = 'ok';
        setTimeout(() => this.saveStatus = 'idle', 3000);
      },
      error: () => {
        this.saving = false;
        this.saveStatus = 'error';
        setTimeout(() => this.saveStatus = 'idle', 4000);
      }
    });
  }
}
