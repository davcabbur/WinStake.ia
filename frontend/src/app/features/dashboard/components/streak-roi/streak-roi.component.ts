import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StreakVM, RoiSportVM, RoiMarketVM } from '../../dashboard.models';

/**
 * Streak strip (handoff §7.9) + ROI by Sport/Market (§7.10) con bullet bars
 * divergentes desde el centro (cero). Datos reales derivados del historial.
 */
@Component({
  selector: 'app-streak-roi',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="panel">
      <div class="kicker">STREAK · LAST 14</div>
      <div class="strip">
        <div class="sq" *ngFor="let s of streak.results" [class.w]="s === 'W'" [class.l]="s === 'L'">{{ s }}</div>
        <div class="empty" *ngIf="streak.results.length === 0">Sin resultados aún</div>
      </div>
      <div class="srow" *ngIf="streak.results.length">
        <span>Current:
          <span [class.loss]="streak.currentRun?.type === 'L'" [class.win]="streak.currentRun?.type === 'W'">
            {{ streak.currentRun?.type }}{{ streak.currentRun?.length }}
          </span>
        </span>
        <span>Worst: <span class="loss">L{{ streak.worstLoss }}</span></span>
        <span>Best: <span class="win">W{{ streak.bestWin }}</span></span>
      </div>

      <div class="divider"></div>

      <div class="kicker mb">ROI BY SPORT / MARKET</div>

      <div class="item" *ngFor="let s of roiBySport">
        <div class="ihead">
          <span class="name" [class.nba]="s.sport === 'NBA'" [class.laliga]="s.sport === 'LaLiga'">{{ s.sport.toUpperCase() }}</span>
          <span class="dim">{{ s.bets }} bets · WR {{ s.wr.toFixed(1) }}%</span>
          <span [class.loss]="s.roi < 0" [class.win]="s.roi >= 0">{{ s.roi.toFixed(1) }}%</span>
        </div>
        <div class="bullet">
          <div class="mid"></div>
          <div class="fill" [class.neg]="s.roi < 0" [style.width.%]="barW(s.roi)"
               [style.left]="s.roi >= 0 ? '50%' : 'auto'" [style.right]="s.roi < 0 ? '50%' : 'auto'"></div>
        </div>
      </div>

      <div class="thin"></div>

      <div class="item sm" *ngFor="let m of roiByMarket">
        <div class="ihead">
          <span class="t">{{ m.name }}</span>
          <span class="dim">{{ m.bets }}</span>
          <span [class.loss]="m.roi < 0" [class.win]="m.roi >= 0">{{ m.roi.toFixed(1) }}%</span>
        </div>
        <div class="bullet thin-bar">
          <div class="mid"></div>
          <div class="fill" [class.neg]="m.roi < 0" [style.width.%]="barW(m.roi)"
               [style.left]="m.roi >= 0 ? '50%' : 'auto'" [style.right]="m.roi < 0 ? '50%' : 'auto'"></div>
        </div>
      </div>
      <div class="empty" *ngIf="roiByMarket.length === 0">Sin desglose por mercado.</div>
    </div>
  `,
  styles: [`
    .panel { background: var(--ws-panel); padding: 16px 18px; border-top: 1px solid var(--ws-line2); }
    .kicker { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); letter-spacing: var(--ws-ls-kicker); margin-bottom: 8px; }
    .kicker.mb { margin-bottom: 10px; }

    .strip { display: flex; gap: 3px; margin-bottom: 14px; }
    .sq { flex: 1; height: 26px; display: flex; align-items: center; justify-content: center;
          font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); font-weight: 700; }
    .sq.w { background: var(--ws-win-soft); color: var(--ws-win); border-top: 2px solid var(--ws-win); }
    .sq.l { background: var(--ws-loss-soft); color: var(--ws-loss); border-top: 2px solid var(--ws-loss); }

    .srow { font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); color: var(--ws-dim); display: flex; justify-content: space-between; }
    .win { color: var(--ws-win); font-weight: 700; } .loss { color: var(--ws-loss); font-weight: 700; }
    .dim { color: var(--ws-dim); } .t { color: var(--ws-text); }

    .divider { height: 1px; background: var(--ws-line2); margin: 16px -18px; }
    .thin { height: 1px; background: var(--ws-line); margin: 12px 0; }

    .item { margin-bottom: 10px; } .item.sm { margin-bottom: 8px; }
    .ihead { display: flex; justify-content: space-between; font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); margin-bottom: 4px; }
    .name { font-weight: 700; } .name.nba { color: var(--ws-nba); } .name.laliga { color: var(--ws-laliga); }

    .bullet { height: 4px; background: var(--ws-bg); position: relative; }
    .bullet.thin-bar { height: 3px; }
    .mid { position: absolute; left: 50%; top: 0; height: 100%; width: 1px; background: var(--ws-dim2); }
    .fill { position: absolute; top: 0; height: 100%; background: var(--ws-win); }
    .fill.neg { background: var(--ws-loss); }

    .empty { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim2); }
  `]
})
export class StreakRoiComponent {
  @Input() streak: StreakVM = { results: [], currentRun: null, worstLoss: 0, bestWin: 0 };
  @Input() roiBySport: RoiSportVM[] = [];
  @Input() roiByMarket: RoiMarketVM[] = [];

  // width = |ROI| × 3, clamp a 50% (handoff §7.10).
  barW(roi: number): number { return Math.min(50, Math.abs(roi) * 3); }
}
