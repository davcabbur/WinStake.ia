import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { KpiVM } from '../../dashboard.models';

/**
 * Fila de 6 KPIs (handoff §7.4). Grid repeat(6, 1fr) con 1px de línea visible.
 * Presentacional puro: recibe los KpiVM ya formateados desde el store.
 */
@Component({
  selector: 'app-kpi-row',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="kpis">
      <div class="kpi" *ngFor="let k of kpis">
        <div class="lbl">{{ k.label }}</div>
        <div class="val" [class]="k.tone">{{ k.value }}</div>
        <div class="sub">{{ k.sub }}</div>
      </div>
    </div>
  `,
  styles: [`
    .kpis {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 1px;
      background: var(--ws-line2);
      border-top: 1px solid var(--ws-line2);
      border-bottom: 1px solid var(--ws-line2);
    }
    .kpi { background: var(--ws-panel); padding: 14px 18px; }
    .lbl { font-size: var(--ws-text-kicker); color: var(--ws-dim); letter-spacing: var(--ws-ls-kicker); font-family: var(--ws-font-mono); margin-bottom: 8px; }
    .val { font-size: var(--ws-text-kpi); font-weight: 700; font-family: var(--ws-font-mono); line-height: 1; }
    .sub { font-size: var(--ws-text-kicker); color: var(--ws-dim2); font-family: var(--ws-font-mono); margin-top: 6px; letter-spacing: var(--ws-ls-mono-data); }

    .val.text  { color: var(--ws-text); }
    .val.win   { color: var(--ws-win); }
    .val.loss  { color: var(--ws-loss); }
    .val.amber { color: var(--ws-amber); }
    .val.dim   { color: var(--ws-dim); }

    @media (max-width: 1100px) {
      .kpis { grid-template-columns: repeat(3, 1fr); }
    }
  `]
})
export class KpiRowComponent {
  @Input() kpis: KpiVM[] = [];
}
