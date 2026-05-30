import { ChangeDetectionStrategy, ChangeDetectorRef, Component, Input, OnChanges, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { MarketRow } from '../../dashboard.models';

interface CellView {
  priceStr: string;      // "1.95" o "—"
  isEdge: boolean;
  up: boolean;
  down: boolean;
  flash: '' | 'up' | 'down';
}
interface RowView {
  id: string;
  time: string;
  live: boolean;
  sportClass: 'nba' | 'laliga';
  sportLabel: string;
  match: string;
  one: CellView; x: CellView; two: CellView;
  implStr: string;
  ovr: string;
  ovrTone: 'dim' | 'amber' | 'loss';
  edgeStr: string;
  edgeTone: 'amber' | 'win' | 'dim2';
  hasSpark: boolean;
  sparkPath: string;
  sparkTone: 'win' | 'loss' | 'dim';
  arrow: '' | 'up' | 'down' | 'flat';
  arrowVal: string;
}

const SPARK_W = 70;
const SPARK_H = 18;

/**
 * Market Watch · Live Odds (handoff §7.6) — el componente único de esta dirección.
 * Tabla densa: TIME · SPORT · MATCH · 1 · X · 2 · IMPL% · OVR · EDGE · Δ6H.
 * IMPL% y OVR se calculan en cliente sobre las cuotas reales. El edge del modelo
 * y la sparkline vienen del seed mock (el WS no transporta el modelo todavía);
 * cuando el WS emite cuotas reales, el store las sobreescribe y aquí parpadean.
 */
@Component({
  selector: 'app-market-watch',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="panel">
      <div class="phead">
        <div>
          <div class="kicker">MARKET WATCH · LIVE ODDS · NEXT 8H</div>
          <div class="title">Cotizaciones del mercado
            <span class="meta">· {{ rows.length }} partidos · WS {{ wsConnected ? 'conectado' : 'mock' }}</span>
          </div>
        </div>
        <div class="legend">
          <span class="li"><span class="dot" [class.on]="wsConnected"></span> WS {{ wsConnected ? 'LIVE' : 'OFF' }}</span>
          <span class="li"><span class="edge-key"></span> EDGE DEL MODELO</span>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th class="l">TIME</th>
            <th class="l">SPORT</th>
            <th class="l">MATCH</th>
            <th class="r">1</th>
            <th class="r">X</th>
            <th class="r">2</th>
            <th class="r">IMPL %</th>
            <th class="r">OVR</th>
            <th class="r">EDGE</th>
            <th class="l">Δ 6H</th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let r of views">
            <td class="time">
              <span *ngIf="r.live" class="live"><span class="ldot"></span>{{ r.time }}</span>
              <span *ngIf="!r.live" class="dim">{{ r.time }}</span>
            </td>
            <td class="sport" [class]="r.sportClass">{{ r.sportLabel }}</td>
            <td class="match">{{ r.match }}</td>

            <ng-container *ngTemplateOutlet="cell; context: { $implicit: r.one }"></ng-container>
            <ng-container *ngTemplateOutlet="cell; context: { $implicit: r.x }"></ng-container>
            <ng-container *ngTemplateOutlet="cell; context: { $implicit: r.two }"></ng-container>

            <td class="impl">{{ r.implStr }}</td>
            <td class="ovr" [class]="r.ovrTone">{{ r.ovr }}</td>
            <td class="edge" [class]="r.edgeTone">{{ r.edgeStr }}</td>
            <td class="spark">
              <div class="sparkwrap">
                <svg *ngIf="r.hasSpark" [attr.width]="SPARK_W" [attr.height]="SPARK_H">
                  <polyline fill="none" [attr.points]="r.sparkPath" class="spk" [class]="r.sparkTone" />
                </svg>
                <span *ngIf="r.arrow === 'up'"   class="aw win">▲{{ r.arrowVal }}</span>
                <span *ngIf="r.arrow === 'down'" class="aw loss">▼{{ r.arrowVal }}</span>
                <span *ngIf="r.arrow === 'flat'" class="aw dim2">—</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="foot">
        <span>1·X·2 = local / empate / visitante · IMPL% = prob. implícita · OVR = sobre-redondeo de la casa</span>
        <span>Fuente: The Odds API · 8 casas agregadas · tick 30s</span>
      </div>
    </div>

    <!-- celda de cuota reutilizable -->
    <ng-template #cell let-c>
      <td class="oc" [class.edge]="c.isEdge"
          [class.ws-flash-up]="c.flash === 'up'" [class.ws-flash-down]="c.flash === 'down'">
        <span class="price" [class.edge]="c.isEdge" [class.dim2]="c.priceStr === '—'">{{ c.priceStr }}</span>
        <span *ngIf="c.up"   class="mv up">▲</span>
        <span *ngIf="c.down" class="mv down">▼</span>
      </td>
    </ng-template>
  `,
  styles: [`
    .panel { background: var(--ws-panel); padding: 16px 20px 12px; border-top: 1px solid var(--ws-line2); }
    .phead { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .kicker { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); letter-spacing: var(--ws-ls-kicker); }
    .title { font-size: var(--ws-text-title); font-weight: 600; margin-top: 2px; }
    .title .meta { color: var(--ws-dim); font-weight: 400; font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); margin-left: 6px; }
    .legend { display: flex; align-items: center; gap: 14px; font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); }
    .legend .li { display: inline-flex; align-items: center; gap: 5px; }
    .legend .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ws-dim2); }
    .legend .dot.on { background: var(--ws-win); box-shadow: 0 0 5px var(--ws-win); }
    .edge-key { display: inline-block; width: 10px; height: 10px; background: var(--ws-amber-soft); border-left: 2px solid var(--ws-amber); }

    table { width: 100%; border-collapse: collapse; }
    th { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); font-weight: 500; padding: 6px 6px; letter-spacing: .06em; }
    th.l { text-align: left; } th.r { text-align: right; }
    tr { border-bottom: 1px solid var(--ws-line); }
    thead tr { border-bottom: 1px solid var(--ws-line2); }
    td { padding: 8px 6px; font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); }

    .time .live { color: var(--ws-amber); font-weight: 700; display: inline-flex; align-items: center; }
    .ldot { width: 5px; height: 5px; border-radius: 50%; background: var(--ws-amber); margin-right: 5px; box-shadow: 0 0 4px var(--ws-amber); animation: ws-pulse 1.5s ease-in-out infinite; color: var(--ws-amber); }
    .dim { color: var(--ws-dim); }
    .dim2 { color: var(--ws-dim2); }

    .sport { font-size: var(--ws-text-kicker); font-weight: 700; }
    .sport.nba { color: var(--ws-nba); }
    .sport.laliga { color: var(--ws-laliga); }
    .match { color: var(--ws-text); font-size: var(--ws-text-body); font-weight: 500; font-family: var(--ws-font-sans); }

    .oc { text-align: right; position: relative; border-left: 2px solid transparent; }
    .oc.edge { background: var(--ws-amber-soft); border-left: 2px solid var(--ws-amber); }
    .price { color: var(--ws-text); font-weight: 500; font-size: var(--ws-text-body); }
    .price.edge { color: var(--ws-amber); font-weight: 700; }
    .mv { position: absolute; top: 2px; right: 4px; font-size: 8px; }
    .mv.up { color: var(--ws-win); } .mv.down { color: var(--ws-loss); }

    .impl { text-align: right; color: var(--ws-dim); }
    .ovr { text-align: right; }
    .ovr.dim { color: var(--ws-dim); } .ovr.amber { color: var(--ws-amber); } .ovr.loss { color: var(--ws-loss); }
    .edge { text-align: right; font-size: var(--ws-text-body); font-weight: 700; }
    .edge.amber { color: var(--ws-amber); } .edge.win { color: var(--ws-win); } .edge.dim2 { color: var(--ws-dim2); }

    .sparkwrap { display: flex; align-items: center; gap: 6px; }
    .spk { stroke-width: 1.2; }
    .spk.win { stroke: var(--ws-win); } .spk.loss { stroke: var(--ws-loss); } .spk.dim { stroke: var(--ws-dim); }
    .aw { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); }
    .aw.win { color: var(--ws-win); } .aw.loss { color: var(--ws-loss); } .aw.dim2 { color: var(--ws-dim2); }

    .foot { margin-top: 10px; font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim2); display: flex; justify-content: space-between; border-top: 1px solid var(--ws-line); padding-top: 8px; }
  `]
})
export class MarketWatchComponent implements OnChanges {
  @Input() rows: MarketRow[] = [];
  @Input() wsConnected = false;

  private readonly cdr = inject(ChangeDetectorRef);

  readonly SPARK_W = SPARK_W;
  readonly SPARK_H = SPARK_H;

  views: RowView[] = [];

  /** Última cuota vista por celda (id|side) — para detectar el flash. */
  private lastSeen = new Map<string, number>();

  ngOnChanges() {
    this.views = this.rows.map(r => this.toView(r));
  }

  private toView(r: MarketRow): RowView {
    const impl = (o: number | null) => (o ? (1 / o) * 100 : 0);
    const implStr = r.d !== null
      ? `${impl(r.h).toFixed(0)}/${impl(r.d).toFixed(0)}/${impl(r.a).toFixed(0)}`
      : `${impl(r.h).toFixed(0)} / ${impl(r.a).toFixed(0)}`;
    const ovrVal = impl(r.h) + impl(r.d) + impl(r.a) - 100;
    const ovrTone: RowView['ovrTone'] = ovrVal > 6 ? 'loss' : ovrVal > 4 ? 'amber' : 'dim';

    const edgeStr = r.edgeEV !== null ? `+${r.edgeEV.toFixed(1)}%` : '—';
    const edgeTone: RowView['edgeTone'] = r.edgeEV === null ? 'dim2' : (r.edgeEV >= 5 ? 'amber' : 'win');

    let sparkPath = '', sparkTone: RowView['sparkTone'] = 'dim', arrow: RowView['arrow'] = '', arrowVal = '';
    if (r.spark && r.spark.length > 1) {
      const min = Math.min(...r.spark), max = Math.max(...r.spark), range = (max - min) || 1;
      sparkPath = r.spark.map((v, i) =>
        `${(i / (r.spark!.length - 1)) * SPARK_W},${SPARK_H - 2 - ((v - min) / range) * (SPARK_H - 4)}`).join(' ');
      const trend = r.spark[r.spark.length - 1] - r.spark[0];
      if (Math.abs(trend) < 0.01) { sparkTone = 'dim'; arrow = 'flat'; }
      else if (trend > 0) { sparkTone = 'win'; arrow = 'up'; arrowVal = Math.abs(trend).toFixed(2); }
      else { sparkTone = 'loss'; arrow = 'down'; arrowVal = Math.abs(trend).toFixed(2); }
    }

    return {
      id: r.id, time: r.time, live: r.live,
      sportClass: r.sport === 'NBA' ? 'nba' : 'laliga',
      sportLabel: r.sport.toUpperCase(),
      match: r.match,
      one: this.cell(r.id, 'h', r.h, r.prevH, r.edgeSide === 'h'),
      x:   this.cell(r.id, 'x', r.d, r.prevD, r.edgeSide === 'd'),
      two: this.cell(r.id, 'a', r.a, r.prevA, r.edgeSide === 'a'),
      implStr, ovr: `${ovrVal.toFixed(1)}%`, ovrTone,
      edgeStr, edgeTone,
      hasSpark: !!sparkPath, sparkPath, sparkTone, arrow, arrowVal,
    };
  }

  private cell(id: string, side: string, price: number | null, prev: number | null, isEdge: boolean): CellView {
    const moved = prev !== null && price !== null && Math.abs(price - prev) > 0.005;
    const up = moved && price! > prev!;
    const down = moved && price! < prev!;
    const priceStr = price !== null ? price.toFixed(2) : '—';

    // Flash 600ms cuando el precio cambia respecto al último render (updates del WS).
    let flash: CellView['flash'] = '';
    const key = `${id}|${side}`;
    const seen = this.lastSeen.get(key);
    if (price !== null) {
      if (seen !== undefined && Math.abs(price - seen) > 0.005) {
        flash = price > seen ? 'up' : 'down';
        setTimeout(() => {
          const v = this.views.find(r => r.id === id);
          if (v) {
            const c = side === 'h' ? v.one : side === 'x' ? v.x : v.two;
            c.flash = '';
            this.cdr.markForCheck();
          }
        }, 600);
      }
      this.lastSeen.set(key, price);
    }

    return { priceStr, isEdge, up, down, flash };
  }
}
