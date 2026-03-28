import { Component, Input, OnChanges, SimpleChanges, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { OddsUpdate, LiveOddMatch } from '../../../../core/services/websocket.service';

@Component({
  selector: 'app-live-odds',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="glass-card">
      <div class="header-row">
        <div class="title-with-pulse">
          <h2>Live Odds</h2>
          <span class="live-dot pulse"></span>
        </div>
        <span class="text-secondary text-sm" *ngIf="lastUpdate">Actualizado: {{ lastUpdate | date:'HH:mm:ss' }}</span>
      </div>
      
      <div class="odds-list">
        <div class="match-item" *ngFor="let match of matches">
          <div class="match-teams font-medium">{{ match.home }} vs {{ match.away }}</div>
          <div class="odds-row">
            <div class="odd-box" [ngClass]="getOddHighlight(match.id, 'home_odd')">
              <span class="odd-label">1</span>
              <span class="odd-val">{{ match.home_odd | number:'1.2-2' }}</span>
            </div>
            <div class="odd-box" [ngClass]="getOddHighlight(match.id, 'draw_odd')">
              <span class="odd-label">X</span>
              <span class="odd-val">{{ match.draw_odd | number:'1.2-2' }}</span>
            </div>
            <div class="odd-box" [ngClass]="getOddHighlight(match.id, 'away_odd')">
              <span class="odd-label">2</span>
              <span class="odd-val">{{ match.away_odd | number:'1.2-2' }}</span>
            </div>
          </div>
        </div>
        <div class="empty-state" *ngIf="matches.length === 0">
          Esperando datos en directo...
        </div>
      </div>
    </div>
  `,
  styles: [`
    .header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
    }
    
    .title-with-pulse {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    
    .live-dot {
      width: 8px;
      height: 8px;
      background: var(--status-error-text);
      border-radius: 50%;
    }
    
    .live-dot.pulse {
      box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4);
      animation: pulse-red 2s infinite;
    }
    
    @keyframes pulse-red {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
      70% { box-shadow: 0 0 0 6px rgba(239, 68, 68, 0); }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }
    
    .text-sm { font-size: 12px; }
    .text-secondary { color: var(--text-secondary); }
    .font-medium { font-weight: 500; font-size: 14px; }
    
    .odds-list {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    
    .match-item {
      padding: 16px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.04);
      border-radius: 12px;
    }
    
    .match-teams {
      margin-bottom: 12px;
      color: var(--text-primary);
    }
    
    .odds-row {
      display: flex;
      gap: 8px;
    }
    
    .odd-box {
      flex: 1;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      background: var(--bg-main);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      font-size: 14px;
      transition: background-color 0.5s ease;
    }
    
    .odd-label {
      color: var(--text-secondary);
      font-size: 12px;
      font-weight: 600;
    }
    
    .odd-val {
      color: var(--text-primary);
      font-weight: 600;
      font-variant-numeric: tabular-nums;
    }
    
    /* Highlight Animations */
    .highlight-up {
      background: rgba(16, 185, 129, 0.2);
      border-color: rgba(16, 185, 129, 0.4);
    }
    
    .highlight-down {
      background: rgba(239, 68, 68, 0.2);
      border-color: rgba(239, 68, 68, 0.4);
    }
    
    .empty-state {
      text-align: center;
      color: var(--text-secondary);
      padding: 32px;
    }
  `]
})
export class LiveOddsComponent implements OnChanges, OnDestroy {
  @Input() data: OddsUpdate | null = null;
  
  matches: LiveOddMatch[] = [];
  lastUpdate: Date | null = null;
  
  // Store previous state to determine highlights
  private previousOdds: Record<string, Record<string, number>> = {};
  
  // Store current active highlights
  private activeHighlights: Record<string, Record<string, 'highlight-up' | 'highlight-down' | ''>> = {};
  private highlightTimeouts: any[] = [];

  ngOnChanges(changes: SimpleChanges) {
    if (changes['data'] && this.data) {
      this.lastUpdate = new Date(this.data.timestamp * 1000); // from python time.time()
      
      // Compute highlights
      const incomingMatches = this.data.matches;
      incomingMatches.forEach(match => {
        if (!this.previousOdds[match.id]) {
          this.previousOdds[match.id] = {};
          this.activeHighlights[match.id] = {};
        }
        
        this.checkHighlight(match, 'home_odd');
        this.checkHighlight(match, 'draw_odd');
        this.checkHighlight(match, 'away_odd');
        
        // Save state for next iteration
        this.previousOdds[match.id]['home_odd'] = match.home_odd;
        this.previousOdds[match.id]['draw_odd'] = match.draw_odd;
        this.previousOdds[match.id]['away_odd'] = match.away_odd;
      });
      
      this.matches = incomingMatches;
    }
  }

  private checkHighlight(match: any, field: string) {
    const prev = this.previousOdds[match.id][field];
    const curr = match[field];
    
    if (prev && curr !== prev) {
      const type = curr > prev ? 'highlight-up' : 'highlight-down';
      this.activeHighlights[match.id][field] = type;
      
      // Clear highlight after 1.5s
      const timeout = setTimeout(() => {
        if (this.activeHighlights[match.id]) {
          this.activeHighlights[match.id][field] = '';
        }
      }, 1500);
      this.highlightTimeouts.push(timeout);
    }
  }

  getOddHighlight(matchId: string, field: string): string {
    if (this.activeHighlights[matchId] && this.activeHighlights[matchId][field]) {
      return this.activeHighlights[matchId][field] as string;
    }
    return '';
  }
  
  ngOnDestroy() {
    this.highlightTimeouts.forEach(clearTimeout);
  }
}
