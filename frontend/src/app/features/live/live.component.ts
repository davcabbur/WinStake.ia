import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { WebsocketService, OddsUpdate, LiveOddMatch } from '../../core/services/websocket.service';

@Component({
  selector: 'app-live',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="glass-card status-bar">
      <div class="status-left">
        <span class="live-badge" [class.connected]="isConnected">
          <span class="live-dot" [class.pulse]="isConnected"></span>
          {{ isConnected ? 'Conectado' : 'Desconectado' }}
        </span>
        <span class="text-secondary" *ngIf="lastUpdate">
          Ultima actualizacion: {{ lastUpdate | date:'HH:mm:ss' }}
        </span>
      </div>
      <span class="match-count" *ngIf="matches.length > 0">{{ matches.length }} partidos</span>
    </div>

    <div class="matches-grid" *ngIf="matches.length > 0">
      <div class="glass-card match-card" *ngFor="let match of matches">
        <div class="match-header">
          <span class="match-teams">{{ match.home }} vs {{ match.away }}</span>
        </div>

        <div class="odds-grid">
          <div class="odd-cell" [ngClass]="getHighlight(match.id, 'home_odd')">
            <span class="odd-type">1</span>
            <span class="odd-value">{{ match.home_odd | number:'1.2-2' }}</span>
            <span class="odd-prob text-secondary">{{ (1 / match.home_odd) * 100 | number:'1.0-0' }}%</span>
          </div>
          <div class="odd-cell" [ngClass]="getHighlight(match.id, 'draw_odd')">
            <span class="odd-type">X</span>
            <span class="odd-value">{{ match.draw_odd | number:'1.2-2' }}</span>
            <span class="odd-prob text-secondary">{{ (1 / match.draw_odd) * 100 | number:'1.0-0' }}%</span>
          </div>
          <div class="odd-cell" [ngClass]="getHighlight(match.id, 'away_odd')">
            <span class="odd-type">2</span>
            <span class="odd-value">{{ match.away_odd | number:'1.2-2' }}</span>
            <span class="odd-prob text-secondary">{{ (1 / match.away_odd) * 100 | number:'1.0-0' }}%</span>
          </div>
        </div>

        <!-- Overround indicator -->
        <div class="overround">
          <span class="text-secondary">Overround:</span>
          <span [class.text-warning]="getOverround(match) > 105">
            {{ getOverround(match) | number:'1.1-1' }}%
          </span>
        </div>
      </div>
    </div>

    <div class="glass-card empty-state" *ngIf="matches.length === 0">
      <div class="empty-icon">&#9889;</div>
      <p>Esperando datos en directo...</p>
      <p class="text-secondary small">El WebSocket se reconecta automaticamente cada 5 segundos.</p>
    </div>
  `,
  styles: [`
    .status-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding: 16px 24px;
    }

    .status-left {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .live-badge {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      font-weight: 600;
      color: var(--text-secondary);
    }

    .live-badge.connected { color: var(--status-success-text); }

    .live-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--text-secondary);
    }

    .live-badge.connected .live-dot { background: var(--status-success-text); }

    .live-dot.pulse {
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
      70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
      100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }

    .match-count {
      font-size: 13px;
      color: var(--text-secondary);
    }

    .matches-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 20px;
    }

    .match-card { padding: 20px; }

    .match-teams {
      font-weight: 600;
      font-size: 15px;
      color: var(--text-primary);
    }

    .match-header { margin-bottom: 16px; }

    .odds-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }

    .odd-cell {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 4px;
      padding: 14px 10px;
      background: var(--bg-main);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      transition: background 0.5s, border-color 0.5s;
    }

    .odd-type {
      font-size: 11px;
      font-weight: 600;
      color: var(--text-secondary);
      text-transform: uppercase;
    }

    .odd-value {
      font-size: 20px;
      font-weight: 700;
      color: var(--text-primary);
      font-variant-numeric: tabular-nums;
    }

    .odd-prob {
      font-size: 11px;
    }

    .highlight-up {
      background: rgba(16, 185, 129, 0.15) !important;
      border-color: rgba(16, 185, 129, 0.3) !important;
    }

    .highlight-down {
      background: rgba(239, 68, 68, 0.15) !important;
      border-color: rgba(239, 68, 68, 0.3) !important;
    }

    .overround {
      margin-top: 12px;
      font-size: 12px;
      text-align: right;
      display: flex;
      justify-content: flex-end;
      gap: 6px;
    }

    .text-secondary { color: var(--text-secondary); }
    .text-warning { color: var(--status-warning-text); }

    .empty-state {
      text-align: center;
      padding: 64px 24px;
    }

    .empty-icon {
      font-size: 48px;
      margin-bottom: 16px;
    }

    .empty-state p { margin: 4px 0; }
    .small { font-size: 13px; }
  `]
})
export class LiveComponent implements OnInit, OnDestroy {
  matches: LiveOddMatch[] = [];
  lastUpdate: Date | null = null;
  isConnected = false;

  private wsSub: Subscription | null = null;
  private previousOdds: Record<string, Record<string, number>> = {};
  private highlights: Record<string, Record<string, string>> = {};
  private timeouts: any[] = [];

  constructor(private wsService: WebsocketService) {}

  ngOnInit() {
    this.wsService.connect();
    this.isConnected = true;

    this.wsSub = this.wsService.odds$.subscribe({
      next: (update: OddsUpdate) => {
        this.lastUpdate = new Date(update.timestamp * 1000);
        this.processHighlights(update.matches);
        this.matches = update.matches;
        this.isConnected = true;
      }
    });
  }

  private processHighlights(incoming: LiveOddMatch[]) {
    for (const match of incoming) {
      if (!this.previousOdds[match.id]) {
        this.previousOdds[match.id] = {};
        this.highlights[match.id] = {};
      }

      for (const field of ['home_odd', 'draw_odd', 'away_odd'] as const) {
        const prev = this.previousOdds[match.id][field];
        const curr = (match as any)[field];
        if (prev && curr !== prev) {
          this.highlights[match.id][field] = curr > prev ? 'highlight-up' : 'highlight-down';
          const t = setTimeout(() => {
            if (this.highlights[match.id]) this.highlights[match.id][field] = '';
          }, 2000);
          this.timeouts.push(t);
        }
        this.previousOdds[match.id][field] = curr;
      }
    }
  }

  getHighlight(matchId: string, field: string): string {
    return this.highlights[matchId]?.[field] || '';
  }

  getOverround(match: LiveOddMatch): number {
    return (1 / match.home_odd + 1 / match.draw_odd + 1 / match.away_odd) * 100;
  }

  ngOnDestroy() {
    this.wsSub?.unsubscribe();
    this.wsService.disconnect();
    this.timeouts.forEach(clearTimeout);
  }
}
