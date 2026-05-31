import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { forkJoin } from 'rxjs';
import { ApiService } from '../../services/api.service';

/**
 * Status line del footer (handoff §7.12). Una línea, fondo negro, mono 10px.
 * Tres bloques: atajos | estado de infra | usuario + bankroll.
 */
@Component({
  selector: 'app-status-line',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="status">
      <div class="block">READY · F1 Dashboard · F2 Analysis · F3 History · F4 Live · F5 Settings · ESC menu</div>
      <div class="block center">
        The Odds API <span [class.ok]="apiUp()" [class.off]="!apiUp()">{{ apiUp() ? 'OK' : 'DOWN' }}</span>
      </div>
      <div class="block">WS-001 · BANKROLL {{ bankrollStr() }}</div>
    </div>
  `,
  styles: [`
    .status {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 20px;
      border-top: 1px solid var(--ws-line2);
      background: var(--ws-black);
      font-family: var(--ws-font-mono);
      font-size: var(--ws-text-kicker);
      color: var(--ws-dim);
    }
    .center { text-align: center; }
    .ok  { color: var(--ws-win); }
    .off { color: var(--ws-loss); }
  `]
})
export class StatusLineComponent implements OnInit {
  private readonly api = inject(ApiService);

  readonly apiUp = signal(false);
  readonly bankrollStr = signal('—');

  ngOnInit() {
    forkJoin({
      stats: this.api.getStats(),
      config: this.api.getEngineConfig(),
    }).subscribe({
      next: ({ stats, config }) => {
        this.apiUp.set(true);
        const base = config?.bankroll_base ?? 100;
        const bankroll = base + (stats.total_profit ?? 0);
        this.bankrollStr.set(this.fmtEur(bankroll));
      },
      error: () => this.apiUp.set(false),
    });
  }

  private fmtEur(v: number): string {
    return v.toFixed(2).replace('.', ',') + ' €';
  }
}
