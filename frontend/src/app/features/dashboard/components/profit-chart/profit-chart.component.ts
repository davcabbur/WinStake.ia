import { Component, Input, OnChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChartData } from '../../../../core/services/api.service';
import { LocaleCurrencyPipe } from '../../../../shared/pipes/locale-currency.pipe';

interface DataPoint { x: number; y: number; date: string; value: number; }

@Component({
  selector: 'app-profit-chart',
  standalone: true,
  imports: [CommonModule, LocaleCurrencyPipe],
  template: `
    <div class="glass-card chart-container">
      <div class="chart-header">
        <h2>Curva de Beneficio</h2>
        <div class="chart-legend" *ngIf="chartData && chartData.dates.length > 0">
          <span class="legend-item">
            <span class="legend-dot" [style.background]="isPositive ? '#10b981' : '#ef4444'"></span>
            Profit acumulado
          </span>
        </div>
      </div>

      <div class="chart-body" *ngIf="chartData && chartData.dates.length > 0">

        <!-- Y-axis labels -->
        <div class="y-axis">
          <span class="y-label">{{ maxVal | localeCurrency:0:0 }}</span>
          <span class="y-label">{{ midVal | localeCurrency:0:0 }}</span>
          <span class="y-label">{{ minVal | localeCurrency:0:0 }}</span>
        </div>

        <div class="chart-area" (mousemove)="onMouseMove($event)" (mouseleave)="tooltip = null">
          <svg [attr.viewBox]="'0 0 ' + svgWidth + ' ' + svgHeight" preserveAspectRatio="none" class="chart-svg">
            <!-- Grid lines -->
            <line *ngFor="let y of gridLines"
              [attr.x1]="padding" [attr.y1]="y"
              [attr.x2]="svgWidth - padding" [attr.y2]="y"
              class="grid-line" />

            <!-- Zero line -->
            <line [attr.x1]="padding" [attr.y1]="zeroY"
                  [attr.x2]="svgWidth - padding" [attr.y2]="zeroY"
                  class="zero-line" />

            <defs>
              <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" [attr.stop-color]="isPositive ? '#10b981' : '#ef4444'" stop-opacity="0.3" />
                <stop offset="100%" [attr.stop-color]="isPositive ? '#10b981' : '#ef4444'" stop-opacity="0.02" />
              </linearGradient>
            </defs>

            <path [attr.d]="areaPath" fill="url(#profitGrad)" />
            <path [attr.d]="linePath" fill="none"
              [attr.stroke]="isPositive ? '#10b981' : '#ef4444'"
              stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />

            <!-- Hover indicator line -->
            <line *ngIf="tooltip"
              [attr.x1]="tooltip.x" [attr.y1]="padding"
              [attr.x2]="tooltip.x" [attr.y2]="svgHeight - padding"
              stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="3 3" />

            <!-- Hover dot -->
            <circle *ngIf="tooltip"
              [attr.cx]="tooltip.x" [attr.cy]="tooltip.y" r="4"
              [attr.fill]="isPositive ? '#10b981' : '#ef4444'"
              stroke="var(--bg-main)" stroke-width="2" />

            <!-- Data points (visible on hover via CSS) -->
            <circle *ngFor="let p of dataPoints"
              [attr.cx]="p.x" [attr.cy]="p.y" r="3"
              [attr.fill]="isPositive ? '#10b981' : '#ef4444'"
              class="data-point" />
          </svg>

          <!-- Floating tooltip -->
          <div class="tooltip" *ngIf="tooltip"
            [style.left.px]="tooltipX"
            [style.top.px]="0">
            <div class="tooltip-date">{{ tooltip.date }}</div>
            <div class="tooltip-value" [class.positive]="tooltip.value >= 0" [class.negative]="tooltip.value < 0">
              {{ tooltip.value | localeCurrency:2:2:true }}
            </div>
          </div>
        </div>

        <!-- X-axis labels -->
        <div class="x-labels">
          <span *ngFor="let label of xLabels" class="x-label">{{ label }}</span>
        </div>
      </div>

      <div class="empty-state" *ngIf="!chartData || chartData.dates.length === 0">
        <p>Sin datos de rendimiento aun. Ejecuta analisis y registra resultados para ver la curva.</p>
      </div>
    </div>
  `,
  styles: [`
    .chart-container { margin-bottom: 32px; }
    .chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .chart-legend { display: flex; gap: 16px; }
    .legend-item { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
    .legend-dot { width: 8px; height: 8px; border-radius: 50%; }

    .chart-body { display: flex; flex-direction: column; gap: 0; }
    .y-axis {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      position: absolute;
      right: calc(100% + 4px);
      top: 0; bottom: 20px;
      font-size: 10px;
      color: var(--text-secondary);
      text-align: right;
      pointer-events: none;
    }
    .chart-area { position: relative; }

    .chart-svg { width: 100%; height: 200px; display: block; }

    .grid-line { stroke: var(--border-color); stroke-width: 0.5; stroke-dasharray: 4 4; }
    .zero-line { stroke: var(--text-secondary); stroke-width: 0.5; opacity: 0.4; }
    .data-point { opacity: 0; transition: opacity 0.2s; }
    .chart-svg:hover .data-point { opacity: 0.6; }

    .x-labels { display: flex; justify-content: space-between; padding: 8px 0 0 0; }
    .x-label { font-size: 11px; color: var(--text-secondary); }

    /* Tooltip */
    .tooltip {
      position: absolute;
      background: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 8px 12px;
      pointer-events: none;
      white-space: nowrap;
      transform: translateX(-50%);
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      z-index: 10;
    }
    .tooltip-date { font-size: 11px; color: var(--text-secondary); margin-bottom: 2px; }
    .tooltip-value { font-size: 14px; font-weight: 700; font-variant-numeric: tabular-nums; color: var(--text-primary); }
    .tooltip-value.positive { color: var(--status-success-text); }
    .tooltip-value.negative { color: var(--status-error-text); }

    .empty-state { text-align: center; padding: 40px; color: var(--text-secondary); font-size: 14px; }
  `]
})
export class ProfitChartComponent implements OnChanges {
  @Input() chartData: ChartData | null = null;

  svgWidth = 800;
  svgHeight = 200;
  padding = 10;

  linePath = '';
  areaPath = '';
  dataPoints: DataPoint[] = [];
  gridLines: number[] = [];
  xLabels: string[] = [];
  zeroY = 100;
  isPositive = true;
  minVal = 0;
  maxVal = 0;
  midVal = 0;

  tooltip: { x: number; y: number; date: string; value: number } | null = null;
  tooltipX = 0;

  ngOnChanges() {
    if (this.chartData && this.chartData.dates.length > 0) this.buildChart();
  }

  private buildChart() {
    const data = this.chartData!;
    const values = data.cumulative_profit;
    const n = values.length;

    this.minVal = Math.min(0, ...values);
    this.maxVal = Math.max(0, ...values);
    this.midVal = Math.round((this.minVal + this.maxVal) / 2);

    const range = this.maxVal - this.minVal || 1;
    const chartW = this.svgWidth - this.padding * 2;
    const chartH = this.svgHeight - this.padding * 2;

    this.isPositive = values[values.length - 1] >= 0;
    this.zeroY = this.padding + ((this.maxVal - 0) / range) * chartH;

    this.gridLines = [0, 1, 2, 3, 4].map(i => this.padding + (i / 4) * chartH);

    this.dataPoints = values.map((val, i) => ({
      x: this.padding + (i / (n - 1 || 1)) * chartW,
      y: this.padding + ((this.maxVal - val) / range) * chartH,
      date: data.dates[i],
      value: val,
    }));

    this.linePath = this.dataPoints.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    const lastX = this.dataPoints[n - 1].x;
    const firstX = this.dataPoints[0].x;
    this.areaPath = this.linePath + ` L ${lastX} ${this.zeroY} L ${firstX} ${this.zeroY} Z`;

    const step = Math.max(1, Math.floor(n / 6));
    this.xLabels = [];
    for (let i = 0; i < n; i += step) this.xLabels.push(data.dates[i].substring(5));
    const last = data.dates[n - 1].substring(5);
    if (this.xLabels[this.xLabels.length - 1] !== last) this.xLabels.push(last);
  }

  onMouseMove(event: MouseEvent) {
    if (!this.dataPoints.length) return;
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    const relX = event.clientX - rect.left;
    const svgRelX = (relX / rect.width) * this.svgWidth;

    // Find nearest data point
    let nearest = this.dataPoints[0];
    let minDist = Math.abs(svgRelX - nearest.x);
    for (const p of this.dataPoints) {
      const d = Math.abs(svgRelX - p.x);
      if (d < minDist) { minDist = d; nearest = p; }
    }

    this.tooltip = { x: nearest.x, y: nearest.y, date: nearest.date, value: nearest.value };
    // Convert SVG X to pixel X for the div tooltip
    this.tooltipX = (nearest.x / this.svgWidth) * rect.width;
  }
}
