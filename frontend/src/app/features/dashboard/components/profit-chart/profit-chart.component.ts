import { Component, Input, OnChanges, ElementRef, ViewChild, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChartData } from '../../../../core/services/api.service';

@Component({
  selector: 'app-profit-chart',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="glass-card chart-container">
      <div class="chart-header">
        <h2>Curva de Beneficio</h2>
        <div class="chart-legend" *ngIf="chartData && chartData.dates.length > 0">
          <span class="legend-item">
            <span class="legend-dot"></span>
            Profit acumulado
          </span>
        </div>
      </div>

      <div class="chart-body" *ngIf="chartData && chartData.dates.length > 0">
        <svg #chartSvg [attr.viewBox]="'0 0 ' + svgWidth + ' ' + svgHeight" preserveAspectRatio="none" class="chart-svg">
          <!-- Grid lines -->
          <line *ngFor="let y of gridLines"
            [attr.x1]="padding" [attr.y1]="y"
            [attr.x2]="svgWidth - padding" [attr.y2]="y"
            class="grid-line" />

          <!-- Zero line -->
          <line
            [attr.x1]="padding" [attr.y1]="zeroY"
            [attr.x2]="svgWidth - padding" [attr.y2]="zeroY"
            class="zero-line" />

          <!-- Gradient fill -->
          <defs>
            <linearGradient id="profitGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" [attr.stop-color]="isPositive ? '#10b981' : '#ef4444'" stop-opacity="0.3" />
              <stop offset="100%" [attr.stop-color]="isPositive ? '#10b981' : '#ef4444'" stop-opacity="0.02" />
            </linearGradient>
          </defs>

          <!-- Area fill -->
          <path [attr.d]="areaPath" fill="url(#profitGrad)" />

          <!-- Line -->
          <path [attr.d]="linePath" fill="none"
            [attr.stroke]="isPositive ? '#10b981' : '#ef4444'"
            stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />

          <!-- Data points -->
          <circle *ngFor="let point of dataPoints"
            [attr.cx]="point.x" [attr.cy]="point.y" r="3"
            [attr.fill]="isPositive ? '#10b981' : '#ef4444'"
            class="data-point" />
        </svg>

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
    .chart-container {
      margin-bottom: 32px;
    }

    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
    }

    .chart-legend {
      display: flex;
      gap: 16px;
    }

    .legend-item {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      color: var(--text-secondary);
    }

    .legend-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--status-success-text);
    }

    .chart-body {
      position: relative;
    }

    .chart-svg {
      width: 100%;
      height: 200px;
    }

    .grid-line {
      stroke: var(--border-color);
      stroke-width: 0.5;
      stroke-dasharray: 4 4;
    }

    .zero-line {
      stroke: var(--text-secondary);
      stroke-width: 0.5;
      opacity: 0.4;
    }

    .data-point {
      opacity: 0;
      transition: opacity 0.2s;
    }

    .chart-svg:hover .data-point {
      opacity: 1;
    }

    .x-labels {
      display: flex;
      justify-content: space-between;
      padding: 8px 0 0 0;
    }

    .x-label {
      font-size: 11px;
      color: var(--text-secondary);
    }

    .empty-state {
      text-align: center;
      padding: 40px;
      color: var(--text-secondary);
      font-size: 14px;
    }
  `]
})
export class ProfitChartComponent implements OnChanges {
  @Input() chartData: ChartData | null = null;

  svgWidth = 800;
  svgHeight = 200;
  padding = 10;

  linePath = '';
  areaPath = '';
  dataPoints: { x: number; y: number }[] = [];
  gridLines: number[] = [];
  xLabels: string[] = [];
  zeroY = 100;
  isPositive = true;

  ngOnChanges() {
    if (this.chartData && this.chartData.dates.length > 0) {
      this.buildChart();
    }
  }

  private buildChart() {
    const data = this.chartData!;
    const values = data.cumulative_profit;
    const n = values.length;

    const minVal = Math.min(0, ...values);
    const maxVal = Math.max(0, ...values);
    const range = maxVal - minVal || 1;

    const chartW = this.svgWidth - this.padding * 2;
    const chartH = this.svgHeight - this.padding * 2;

    this.isPositive = values[values.length - 1] >= 0;

    // Calculate zero line Y
    this.zeroY = this.padding + ((maxVal - 0) / range) * chartH;

    // Grid lines (4 lines)
    this.gridLines = [];
    for (let i = 0; i <= 4; i++) {
      this.gridLines.push(this.padding + (i / 4) * chartH);
    }

    // Map data to SVG coordinates
    this.dataPoints = values.map((val, i) => ({
      x: this.padding + (i / (n - 1 || 1)) * chartW,
      y: this.padding + ((maxVal - val) / range) * chartH,
    }));

    // Build line path
    this.linePath = this.dataPoints
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`)
      .join(' ');

    // Build area path (line + close to zero line)
    const lastX = this.dataPoints[n - 1].x;
    const firstX = this.dataPoints[0].x;
    this.areaPath = this.linePath + ` L ${lastX} ${this.zeroY} L ${firstX} ${this.zeroY} Z`;

    // X-axis labels (show max 6)
    const step = Math.max(1, Math.floor(n / 6));
    this.xLabels = [];
    for (let i = 0; i < n; i += step) {
      const date = data.dates[i];
      this.xLabels.push(date.substring(5)); // MM-DD
    }
    // Always include last
    const lastDate = data.dates[n - 1];
    if (this.xLabels[this.xLabels.length - 1] !== lastDate.substring(5)) {
      this.xLabels.push(lastDate.substring(5));
    }
  }
}
