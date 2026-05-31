import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';

interface TickerItem {
  code: string;          // "RMA-ATM" (3+3 letras casa-casa)
  h: number;
  d: number | null;
  a: number;
  move: number | null;   // movimiento de la cuota recomendada (+/-) o null
}

/**
 * Ticker strip estilo Bloomberg (handoff §7.1).
 * Fondo negro, mono 11px, scroll horizontal continuo. Timestamp UTC real a la derecha.
 *
 * HANDOFF-DEVIATION: las cotizaciones del ticker son mock. El WS actual
 * (/api/ws/odds) sólo emite home/away/draw sin movimiento ni histórico, y
 * además está marcado como mock en el codebase. Cuando exista el WS de cuotas
 * reales enriquecido, alimentar `items` desde LiveOddsService.
 */
@Component({
  selector: 'app-ticker-strip',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="ticker">
      <div class="track">
        <span class="live">● LIVE</span>
        <span class="tk" *ngFor="let t of items">
          {{ t.code }}
          <span class="v">{{ t.h.toFixed(2) }}</span> /
          <span class="v">{{ t.d !== null ? t.d.toFixed(2) : '—' }}</span> /
          <span class="v">{{ t.a.toFixed(2) }}</span>
          <span class="up"   *ngIf="t.move !== null && t.move > 0">▲{{ absMove(t.move) }}</span>
          <span class="down" *ngIf="t.move !== null && t.move < 0">▼{{ absMove(t.move) }}</span>
        </span>
      </div>
      <span class="clock">{{ utc() }}</span>
    </div>
  `,
  styles: [`
    .ticker {
      height: 24px;
      background: var(--ws-black);
      border-bottom: 1px solid var(--ws-line2);
      font-family: var(--ws-font-mono);
      font-size: var(--ws-text-meta);
      color: var(--ws-dim);
      padding: 0 20px;
      display: flex;
      align-items: center;
      gap: 28px;
      overflow: hidden;
      white-space: nowrap;
    }
    .track {
      display: flex;
      align-items: center;
      gap: 28px;
      flex: 1;
      overflow: hidden;
      animation: ticker-scroll 48s linear infinite;
    }
    .ticker:hover .track { animation-play-state: paused; }
    @keyframes ticker-scroll {
      0%   { transform: translateX(0); }
      100% { transform: translateX(-35%); }
    }
    .live { color: var(--ws-amber); font-weight: 700; flex: none; }
    .tk { flex: none; }
    .v    { color: var(--ws-text); }
    .up   { color: var(--ws-win); }
    .down { color: var(--ws-loss); }
    .clock { flex: none; color: var(--ws-dim); }
  `]
})
export class TickerStripComponent implements OnInit, OnDestroy {
  items: TickerItem[] = [];

  readonly utc = signal('');
  private timer: ReturnType<typeof setInterval> | null = null;
  private readonly months = ['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC'];

  ngOnInit() {
    this.tick();
    this.timer = setInterval(() => this.tick(), 1000);
  }

  ngOnDestroy() {
    if (this.timer !== null) clearInterval(this.timer);
  }

  absMove(m: number): string {
    return Math.abs(m).toFixed(2);
  }

  private tick() {
    const now = new Date();
    const p = (n: number) => String(n).padStart(2, '0');
    const date = `${p(now.getUTCDate())} ${this.months[now.getUTCMonth()]} ${now.getUTCFullYear()}`;
    const time = `${p(now.getUTCHours())}:${p(now.getUTCMinutes())}:${p(now.getUTCSeconds())}`;
    this.utc.set(`${date} · ${time} UTC`);
  }
}
