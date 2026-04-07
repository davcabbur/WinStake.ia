import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, NavigationEnd } from '@angular/router';
import { Subscription, filter } from 'rxjs';
import { ApiService } from '../../services/api.service';

interface PageInfo {
  title: string;
  subtitle: string;
}

const PAGE_MAP: Record<string, PageInfo> = {
  '/': { title: 'Dashboard', subtitle: 'Metricas y rendimiento del sistema de analisis' },
  '/analysis': { title: 'Analisis', subtitle: 'Ejecutar y revisar analisis de value bets' },
  '/history': { title: 'Historico', subtitle: 'Registro completo de apuestas y resultados' },
  '/live': { title: 'En Directo', subtitle: 'Odds en tiempo real via WebSocket' },
  '/settings': { title: 'Ajustes', subtitle: 'Configuracion del motor y sistema' },
};

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <header class="topbar">
      <div class="greeting">
        <h1>{{ pageTitle }}</h1>
        <p class="subtitle">{{ pageSubtitle }}</p>
      </div>

      <div class="actions">
        <div class="balance-badge">
          <span class="label">Bankroll</span>
          <span class="value" [class.positive]="bankroll > 100" [class.negative]="bankroll < 100">
            {{ bankroll | number:'1.1-1' }} U
          </span>
        </div>
        <div class="balance-badge">
          <span class="label">Profit</span>
          <span class="value" [class.positive]="profit > 0" [class.negative]="profit < 0">
            {{ profit > 0 ? '+' : '' }}{{ profit | number:'1.2-2' }} U
          </span>
        </div>
      </div>
    </header>
  `,
  styles: [`
    .topbar {
      padding: 28px 40px;
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

    .actions {
      display: flex;
      gap: 12px;
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
      font-variant-numeric: tabular-nums;
    }

    .value.positive { color: var(--status-success-text); }
    .value.negative { color: var(--status-error-text); }

    @media (max-width: 768px) {
      .topbar { padding: 20px 16px; }
      .actions { gap: 8px; }
      .balance-badge { padding: 6px 12px; }
    }
  `]
})
export class TopbarComponent implements OnInit, OnDestroy {
  pageTitle = 'Dashboard';
  pageSubtitle = 'Metricas y rendimiento del sistema de analisis';
  bankroll = 100.0;
  profit = 0;

  private routerSub: Subscription | null = null;

  constructor(private router: Router, private api: ApiService) {}

  ngOnInit() {
    this.updatePage(this.router.url);
    this.routerSub = this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe(e => this.updatePage(e.urlAfterRedirects));

    this.api.getStats().subscribe({
      next: (stats) => {
        this.profit = stats.total_profit;
        this.bankroll = 100 + stats.total_profit;
      },
      error: () => {}
    });
  }

  private updatePage(url: string) {
    const info = PAGE_MAP[url] || PAGE_MAP['/'];
    this.pageTitle = info.title;
    this.pageSubtitle = info.subtitle;
  }

  ngOnDestroy() {
    this.routerSub?.unsubscribe();
  }
}
