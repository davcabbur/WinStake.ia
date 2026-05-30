import { ChangeDetectionStrategy, Component, Input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PickVM } from '../../dashboard.models';

type Filter = 'ALL' | 'NBA' | 'LALIGA';

/**
 * Picks Blotter (handoff §7.7) — últimas 10 apuestas resueltas/pendientes.
 * Tabla densa mono. Filtros de deporte (ALL activo; el historial actual es NBA).
 */
@Component({
  selector: 'app-picks-blotter',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="panel">
      <div class="phead">
        <div>
          <div class="kicker">BLOTTER · LAST 10 PICKS</div>
          <div class="title">Historial de Apuestas</div>
        </div>
        <div class="filters">
          <span *ngFor="let f of filterOpts" class="fbtn" [class.on]="f === filter()" (click)="filter.set(f)">{{ f }}</span>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th class="l">DATE</th><th class="l">SPORT</th><th class="l">MATCH</th><th class="l">SELECTION</th>
            <th class="r">ODDS</th><th class="r">EV%</th><th class="l">CONF</th><th class="r">STAKE</th>
            <th class="r">P/L</th><th class="l">RESULT</th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let p of filtered()">
            <td class="dim">{{ p.date }}</td>
            <td class="sport" [class.nba]="p.sport === 'NBA'" [class.laliga]="p.sport === 'LaLiga'">{{ p.sport }}</td>
            <td class="match">{{ p.match }}</td>
            <td class="t">{{ p.selection }}</td>
            <td class="r t">{{ p.odds.toFixed(2) }}</td>
            <td class="r win">+{{ p.ev.toFixed(1) }}</td>
            <td class="conf" [class]="confTone(p.conf)">{{ up(p.conf) }}</td>
            <td class="r t">{{ p.stake.toFixed(2) }} €</td>
            <td class="r" [class.win]="(p.profit ?? 0) > 0" [class.loss]="(p.profit ?? 0) < 0" [class.dim]="p.profit === null">
              {{ p.profit === null ? '—' : (p.profit > 0 ? '+' : '') + p.profit.toFixed(2) + ' €' }}
            </td>
            <td class="res">
              <span *ngIf="p.result === 'Ganada'"   class="win">● WIN</span>
              <span *ngIf="p.result === 'Perdida'"   class="loss">● LOSS</span>
              <span *ngIf="p.result === 'Pendiente'" class="pend">○ PEND</span>
            </td>
          </tr>
          <tr *ngIf="filtered().length === 0">
            <td colspan="10" class="empty">Sin apuestas registradas.</td>
          </tr>
        </tbody>
      </table>
    </div>
  `,
  styles: [`
    .panel { background: var(--ws-panel); padding: 16px 20px; border-top: 1px solid var(--ws-line2); }
    .phead { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
    .kicker { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); letter-spacing: var(--ws-ls-kicker); }
    .title { font-size: var(--ws-text-title); font-weight: 600; margin-top: 2px; }

    .filters { font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); color: var(--ws-dim); }
    .fbtn { padding: 4px 10px; margin-left: 4px; border: 1px solid var(--ws-line2); cursor: pointer; }
    .fbtn.on { background: var(--ws-bg); color: var(--ws-amber); border-color: var(--ws-amber); }

    table { width: 100%; border-collapse: collapse; font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); }
    th { color: var(--ws-dim); font-weight: 500; padding: 6px 10px 6px 0; letter-spacing: .05em; }
    th.l { text-align: left; } th.r { text-align: right; }
    thead tr { border-bottom: 1px solid var(--ws-line2); }
    tbody tr { border-bottom: 1px solid var(--ws-line); }
    tbody tr:hover td { background: rgba(255,255,255,0.02); }
    td { padding: 8px 10px 8px 0; }
    td.r { text-align: right; }

    .dim { color: var(--ws-dim); }
    .t { color: var(--ws-text); }
    .win { color: var(--ws-win); font-weight: 700; }
    .loss { color: var(--ws-loss); font-weight: 700; }
    .pend { color: var(--ws-pending); font-weight: 700; }
    .match { color: var(--ws-text); font-family: var(--ws-font-sans); font-size: var(--ws-text-body); }
    .sport { font-weight: 600; }
    .sport.nba { color: var(--ws-nba); } .sport.laliga { color: var(--ws-laliga); }
    .conf { font-weight: 600; }
    .conf.alta { color: var(--ws-win); } .conf.media { color: var(--ws-amber); } .conf.baja { color: var(--ws-dim); }

    .empty { text-align: center; color: var(--ws-dim); padding: 32px; }
  `]
})
export class PicksBlotterComponent {
  @Input() picks: PickVM[] = [];

  readonly filterOpts: Filter[] = ['ALL', 'NBA', 'LALIGA'];
  readonly filter = signal<Filter>('ALL');

  filtered(): PickVM[] {
    const f = this.filter();
    if (f === 'ALL') return this.picks;
    const target = f === 'NBA' ? 'NBA' : 'LaLiga';
    return this.picks.filter(p => p.sport === target);
  }

  up(c: string): string { return (c || '').toUpperCase(); }

  confTone(c: string): string {
    return c === 'Alta' ? 'alta' : c === 'Media' ? 'media' : 'baja';
  }
}
