import { ChangeDetectionStrategy, Component, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChartPoint, ChartStats } from '../../dashboard.models';

interface YTick { v: number; y: number; zero: boolean; label: string; }
interface XTick { x: number; label: string; }
interface Seg { points: string; win: boolean; }

/**
 * Curva de beneficio (handoff §7.5). SVG inline, línea bicolor (win/loss según
 * el signo), línea de cero sólida, resto de grid punteado. Sin gradientes ni
 * sombras. Presentacional puro: recibe los puntos ya calculados.
 */
@Component({
  selector: 'app-profit-chart',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="panel">
      <div class="phead">
        <div>
          <div class="kicker">CHART · P/L CUMULATIVE · {{ points.length }}D</div>
          <div class="title">Curva de Beneficio</div>
        </div>
        <div class="hstats" *ngIf="stats">
          <span>HIGH <span class="win">{{ eur(stats.high) }}</span> · {{ stats.highDate }}</span>
          <span>LOW <span class="loss">{{ eur(stats.low) }}</span> · {{ stats.lowDate }}</span>
          <span>VOL σ <span class="t">{{ eur(stats.vol, false) }}</span></span>
        </div>
      </div>

      <svg *ngIf="points.length > 1" [attr.viewBox]="'0 0 ' + W + ' ' + H" width="100%" [attr.height]="H" class="chart">
        <g class="grid">
          <line *ngFor="let t of yTicks" [attr.x1]="padL" [attr.x2]="W - padR" [attr.y1]="t.y" [attr.y2]="t.y"
                [class.zero]="t.zero" [class.dash]="!t.zero" />
          <text *ngFor="let t of yTicks" class="axis" [attr.x]="padL - 8" [attr.y]="t.y + 4" text-anchor="end">{{ t.label }}</text>
        </g>
        <text *ngFor="let t of xTicks" class="axis" [attr.x]="t.x" [attr.y]="H - 10" text-anchor="middle">{{ t.label }}</text>

        <polyline *ngFor="let s of segments" class="seg" [class.win]="s.win" [class.loss]="!s.win"
                  fill="none" [attr.points]="s.points" />

        <g *ngIf="last">
          <circle [attr.cx]="last.x" [attr.cy]="last.y" r="3" class="dot-loss" />
          <rect [attr.x]="last.x - 56" [attr.y]="last.y - 22" width="52" height="16" class="lbl-box" />
          <text [attr.x]="last.x - 30" [attr.y]="last.y - 11" text-anchor="middle" class="lbl-txt">{{ last.label }}</text>
        </g>
      </svg>

      <div class="empty" *ngIf="points.length <= 1">
        Sin datos de rendimiento suficientes. Registra resultados para ver la curva.
      </div>
    </div>
  `,
  styles: [`
    .panel { background: var(--ws-panel); padding: 16px 20px; }
    .phead { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 6px; }
    .kicker { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); letter-spacing: var(--ws-ls-kicker); }
    .title { font-size: var(--ws-text-title); font-weight: 600; margin-top: 2px; }
    .hstats { display: flex; gap: 16px; font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); color: var(--ws-dim); }
    .hstats .win { color: var(--ws-win); }
    .hstats .loss { color: var(--ws-loss); }
    .hstats .t { color: var(--ws-text); }

    .chart { display: block; }
    .grid line.zero { stroke: var(--ws-line2); }
    .grid line.dash { stroke: var(--ws-line); stroke-dasharray: 2 4; }
    .axis { fill: var(--ws-dim); font-size: 11px; font-family: var(--ws-font-mono); }
    .seg { stroke-width: 1.6; }
    .seg.win { stroke: var(--ws-win); }
    .seg.loss { stroke: var(--ws-loss); }
    .dot-loss { fill: var(--ws-loss); }
    .lbl-box { fill: var(--ws-loss); fill-opacity: 0.15; stroke: var(--ws-loss); stroke-opacity: 0.4; }
    .lbl-txt { fill: var(--ws-loss); font-size: 10px; font-family: var(--ws-font-mono); }

    .empty { text-align: center; padding: 60px 20px; color: var(--ws-dim); font-size: var(--ws-text-body); }
  `]
})
export class ProfitChartComponent implements OnChanges {
  @Input() points: ChartPoint[] = [];
  @Input() stats: ChartStats | null = null;

  readonly W = 1352;
  readonly H = 320;
  readonly padL = 56;
  readonly padR = 16;
  readonly padT = 24;
  readonly padB = 32;

  yTicks: YTick[] = [];
  xTicks: XTick[] = [];
  segments: Seg[] = [];
  last: { x: number; y: number; label: string } | null = null;

  ngOnChanges() {
    this.build();
  }

  eur(v: number, sign = true): string {
    const s = v.toFixed(2).replace('.', ',') + ' €';
    return sign && v > 0 ? '+' + s : s;
  }

  private build() {
    const data = this.points;
    if (data.length <= 1) { this.yTicks = []; this.xTicks = []; this.segments = []; this.last = null; return; }

    const vals = data.map(p => p.v);
    const min = Math.min(...vals, 0);
    const max = Math.max(...vals, 0);
    const range = (max - min) || 1;

    const x = (i: number) => this.padL + (this.W - this.padL - this.padR) * (i / (data.length - 1));
    const y = (v: number) => this.padT + (this.H - this.padT - this.padB) * (1 - (v - min) / range);
    const zeroY = y(0);

    // Y ticks
    this.yTicks = [max, max * 0.5, 0, min * 0.5, min].map(v => {
      const r = Math.round(v);
      return { v: r, y: y(r), zero: r === 0, label: `${r >= 0 ? '+' : ''}${r}€` };
    });

    // X ticks — 6 índices repartidos
    this.xTicks = [0, 1, 2, 3, 4, 5].map(k => {
      const i = Math.round((k * (data.length - 1)) / 5);
      return { x: x(i), label: data[i].d };
    });

    // Segmentos bicolor con intersección en y=0
    const segs: Seg[] = [];
    let cur: { sign: number; pts: [number, number][] } = { sign: data[0].v >= 0 ? 1 : -1, pts: [[x(0), y(data[0].v)]] };
    for (let i = 1; i < data.length; i++) {
      const sgn = data[i].v >= 0 ? 1 : -1;
      if (sgn !== cur.sign) {
        const v0 = data[i - 1].v, v1 = data[i].v;
        const t = v0 / (v0 - v1);
        const xi = x(i - 1) + (x(i) - x(i - 1)) * t;
        cur.pts.push([xi, zeroY]);
        segs.push({ points: ptsToStr(cur.pts), win: cur.sign === 1 });
        cur = { sign: sgn, pts: [[xi, zeroY], [x(i), y(data[i].v)]] };
      } else {
        cur.pts.push([x(i), y(data[i].v)]);
      }
    }
    segs.push({ points: ptsToStr(cur.pts), win: cur.sign === 1 });
    this.segments = segs;

    const lastPt = data[data.length - 1];
    this.last = {
      x: x(data.length - 1),
      y: y(lastPt.v),
      label: lastPt.v.toFixed(2).replace('.', ',') + '€',
    };
  }
}

function ptsToStr(pts: [number, number][]): string {
  return pts.map(p => `${p[0]},${p[1]}`).join(' ');
}
