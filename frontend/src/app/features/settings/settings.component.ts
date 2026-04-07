import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule],
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

      <!-- Engine Parameters -->
      <div class="glass-card">
        <h2>Parametros del Motor</h2>
        <div class="params-list">
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Modelo</span>
              <span class="param-desc text-secondary">Distribucion de Poisson para probabilidades</span>
            </div>
            <span class="param-value">Poisson</span>
          </div>
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">EV Minimo</span>
              <span class="param-desc text-secondary">Umbral para considerar value bet</span>
            </div>
            <span class="param-value">3.0%</span>
          </div>
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Kelly</span>
              <span class="param-desc text-secondary">Half-Kelly para sizing conservador</span>
            </div>
            <span class="param-value">50%</span>
          </div>
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Kelly Cap</span>
              <span class="param-desc text-secondary">Maximo % del bankroll por apuesta</span>
            </div>
            <span class="param-value">25%</span>
          </div>
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Ventaja Local</span>
              <span class="param-desc text-secondary">Factor multiplicador para equipo local</span>
            </div>
            <span class="param-value">1.25x</span>
          </div>
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Peso xG</span>
              <span class="param-desc text-secondary">Blending de Expected Goals vs goles reales</span>
            </div>
            <span class="param-value">65/35</span>
          </div>
          <div class="param-item">
            <div class="param-info">
              <span class="param-name">Bankroll Base</span>
              <span class="param-desc text-secondary">Unidades iniciales de referencia</span>
            </div>
            <span class="param-value">100 U</span>
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

    .param-desc {
      font-size: 12px;
    }

    .param-value {
      font-size: 14px;
      font-weight: 600;
      color: var(--accent-primary);
      font-variant-numeric: tabular-nums;
    }

    .text-secondary { color: var(--text-secondary); }

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
    }
  `]
})
export class SettingsComponent implements OnInit {
  apiStatus: 'checking' | 'ok' | 'error' = 'checking';

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.http.get<any>('http://localhost:8000/health').subscribe({
      next: () => this.apiStatus = 'ok',
      error: () => this.apiStatus = 'error'
    });
  }
}
