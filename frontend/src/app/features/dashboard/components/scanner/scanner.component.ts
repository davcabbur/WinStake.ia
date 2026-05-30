import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ScannerPickVM } from '../../dashboard.models';

/**
 * Top Value Bets / Scanner (handoff §7.8). Lista de cards con barra comparativa
 * modelo (MDL, ámbar) vs mercado (MKT, dim). Datos reales vía /api/v1/analysis.
 */
@Component({
  selector: 'app-scanner',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="panel">
      <div class="kicker">SCANNER · NEXT 6H</div>
      <div class="title">
        <span>Top Value Bets</span>
        <span class="alerts" *ngIf="picks.length">{{ picks.length }} ALERTS</span>
      </div>

      <div class="state" *ngIf="loading">Analizando mercado…</div>
      <div class="state" *ngIf="!loading && error">Análisis no disponible ahora.</div>
      <div class="state" *ngIf="!loading && !error && picks.length === 0">Sin oportunidades de valor.</div>

      <div class="card" *ngFor="let p of picks" [class.high]="p.conf === 'Alta'">
        <div class="chead">
          <span class="sp" [class.nba]="p.sport === 'NBA'" [class.laliga]="p.sport === 'LaLiga'">{{ p.sport }} · {{ p.time }}</span>
          <span class="ev">EV +{{ p.ev.toFixed(1) }}%</span>
        </div>
        <div class="match">{{ p.match }}</div>
        <div class="sel">
          <span>{{ p.selection }} &#64; <span class="t">{{ p.odds.toFixed(2) }}</span></span>
          <span>K½ <span class="amber">{{ p.kelly.toFixed(2) }}%</span></span>
        </div>
        <div class="bars">
          <div class="bar">
            <span class="bl">MDL</span>
            <div class="track"><div class="fill mdl" [style.width.%]="pct(p.modelProb)"></div></div>
            <span class="bv">{{ pct(p.modelProb).toFixed(1) }}%</span>
          </div>
          <div class="bar">
            <span class="bl">MKT</span>
            <div class="track"><div class="fill mkt" [style.width.%]="pct(p.marketProb)"></div></div>
            <span class="bv">{{ pct(p.marketProb).toFixed(1) }}%</span>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .panel { background: var(--ws-panel); padding: 16px 18px; }
    .kicker { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); letter-spacing: var(--ws-ls-kicker); margin-bottom: 4px; }
    .title { font-size: var(--ws-text-title); font-weight: 600; margin-bottom: 12px; display: flex; justify-content: space-between; }
    .alerts { font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); color: var(--ws-amber); font-weight: 700; }
    .state { font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); color: var(--ws-dim); padding: 8px 0; }

    .card { background: var(--ws-panel2); padding: 10px 12px; margin-bottom: 6px; border-left: 2px solid var(--ws-dim2); }
    .card.high { border-left-color: var(--ws-amber); }
    .chead { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
    .sp { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); font-weight: 700; }
    .sp.nba { color: var(--ws-nba); } .sp.laliga { color: var(--ws-laliga); }
    .ev { font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); color: var(--ws-win); font-weight: 700; }
    .match { font-size: var(--ws-text-body); font-weight: 600; margin-bottom: 4px; }
    .sel { display: flex; justify-content: space-between; font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); color: var(--ws-dim); }
    .sel .t { color: var(--ws-text); } .sel .amber { color: var(--ws-amber); }

    .bars { margin-top: 6px; font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); }
    .bar { display: flex; align-items: center; gap: 4px; margin-bottom: 2px; }
    .bl { width: 28px; }
    .track { flex: 1; height: 6px; background: var(--ws-bg); position: relative; }
    .fill { height: 100%; }
    .fill.mdl { background: var(--ws-amber); }
    .fill.mkt { background: var(--ws-dim); }
    .bv { width: 40px; text-align: right; color: var(--ws-text); }
  `]
})
export class ScannerComponent {
  @Input() picks: ScannerPickVM[] = [];
  @Input() loading = false;
  @Input() error = false;

  pct(p: number): number { return Math.max(0, Math.min(100, p * 100)); }
}
