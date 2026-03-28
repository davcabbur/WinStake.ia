import { Component } from '@angular/core';

@Component({
  selector: 'app-topbar',
  standalone: true,
  template: `
    <header class="topbar">
      <div class="greeting">
        <h1>Overview</h1>
        <p class="subtitle">Métricas y rendimiento del sistema de análisis</p>
      </div>
      
      <div class="actions">
        <div class="balance-badge">
          <span class="label">Bankroll</span>
          <span class="value">100.0 U</span>
        </div>
      </div>
    </header>
  `,
  styles: [`
    .topbar {
      padding: 32px 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--bg-main);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    
    .subtitle {
      color: var(--text-secondary);
      margin-top: 4px;
      font-size: 14px;
    }
    
    .balance-badge {
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      padding: 8px 16px;
      border-radius: 12px;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
    }
    
    .balance-badge .label {
      font-size: 11px;
      color: var(--text-secondary);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    
    .balance-badge .value {
      font-size: 16px;
      font-weight: 600;
      color: var(--text-primary);
    }
  `]
})
export class TopbarComponent {}
