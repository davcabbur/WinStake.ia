import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

type Period = '7D' | '30D' | '3M' | 'YTD' | 'TODO';

/**
 * Título de página + filtros de período (handoff §7.3).
 * HANDOFF-DEVIATION: el "próximo ciclo" es un countdown mock — el backend no
 * expone el cron del scheduler. La "última actualización" se fija al cargar.
 * Los botones de período son visuales por ahora (TODO activo); el filtrado por
 * fecha requiere coordinar todos los endpoints y queda fuera de esta tanda.
 */
@Component({
  selector: 'app-page-title',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="ptitle">
      <div class="left">
        <div class="kicker">▎ DASHBOARD / OVERVIEW</div>
        <div class="row">
          <span class="h1">Resumen del Sistema</span>
          <span class="meta">
            Última actualización <span class="v">{{ lastUpdate }}</span>
            · Próximo ciclo en <span class="amber">{{ countdown() }}</span>
          </span>
        </div>
      </div>
      <div class="periods">
        <button *ngFor="let p of periods"
                class="pbtn"
                [class.active]="p === active()"
                (click)="active.set(p)">{{ p }}</button>
      </div>
    </div>
  `,
  styles: [`
    .ptitle { display: flex; align-items: center; justify-content: space-between; padding: 14px 20px 8px; }
    .kicker { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-amber); letter-spacing: var(--ws-ls-kicker-lg); margin-bottom: 4px; }
    .row { display: flex; align-items: baseline; gap: 16px; }
    .h1 { font-size: var(--ws-text-page); font-weight: 700; }
    .meta { font-family: var(--ws-font-mono); font-size: var(--ws-text-body); color: var(--ws-dim); }
    .meta .v { color: var(--ws-text); }
    .meta .amber { color: var(--ws-amber); }

    .periods { display: flex; gap: 8px; }
    .pbtn {
      background: transparent;
      color: var(--ws-dim);
      border: 1px solid var(--ws-line2);
      padding: 5px 10px;
      font-size: var(--ws-text-meta);
      font-family: var(--ws-font-mono);
      font-weight: 700;
      letter-spacing: .05em;
      cursor: pointer;
    }
    .pbtn:hover { border-color: var(--ws-amber); color: var(--ws-text); }
    .pbtn.active { background: var(--ws-amber); color: #0a0d12; border-color: var(--ws-amber); }
    .pbtn.active:hover { color: #0a0d12; }
  `]
})
export class PageTitleComponent implements OnInit, OnDestroy {
  readonly periods: Period[] = ['7D', '30D', '3M', 'YTD', 'TODO'];
  readonly active = signal<Period>('TODO');

  lastUpdate = '';
  readonly countdown = signal('00:00');

  private remaining = 48; // segundos, mock
  private timer: ReturnType<typeof setInterval> | null = null;

  ngOnInit() {
    const now = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    this.lastUpdate = `${p(now.getHours())}:${p(now.getMinutes())}:${p(now.getSeconds())}`;
    this.renderCountdown();
    this.timer = setInterval(() => {
      this.remaining = this.remaining > 0 ? this.remaining - 1 : 59;
      this.renderCountdown();
    }, 1000);
  }

  ngOnDestroy() {
    if (this.timer !== null) clearInterval(this.timer);
  }

  private renderCountdown() {
    const m = Math.floor(this.remaining / 60);
    const s = this.remaining % 60;
    this.countdown.set(`${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`);
  }
}
