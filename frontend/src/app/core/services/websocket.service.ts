import { Injectable } from '@angular/core';
import { Subject, Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface LiveOddMatch {
  id: string;
  home: string;
  away: string;
  home_odd: number;
  away_odd: number;
  draw_odd: number;
}

export interface OddsUpdate {
  type: string;
  matches: LiveOddMatch[];
  timestamp: number;
}

@Injectable({ providedIn: 'root' })
export class WebsocketService {
  private socket: WebSocket | null = null;
  private oddsSubject = new Subject<OddsUpdate>();

  public odds$: Observable<OddsUpdate> = this.oddsSubject.asObservable();

  // Reference counting — only close when all consumers disconnect
  private refCount = 0;

  // Exponential backoff state
  private retryDelay = 1000;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly maxRetryDelay = 30_000;

  connect() {
    this.refCount++;
    if (this.socket) return; // already connected, just bump ref count

    const wsBase = environment.apiBaseUrl.replace(/^http/, 'ws');
    this.socket = new WebSocket(`${wsBase}/api/ws/odds`);

    this.socket.onopen = () => {
      this.retryDelay = 1000; // reset backoff on successful connection
    };

    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'odds_update') {
          this.oddsSubject.next(data);
        }
      } catch (e) {
        console.error('Error parsing WS message', e);
      }
    };

    this.socket.onerror = () => {
      // onclose will fire after onerror; let it handle retry
    };

    this.socket.onclose = () => {
      this.socket = null;
      if (this.refCount > 0) {
        // Schedule reconnect with backoff
        this.retryTimer = setTimeout(() => this.reconnect(), this.retryDelay);
        this.retryDelay = Math.min(this.retryDelay * 2, this.maxRetryDelay);
      }
    };
  }

  private reconnect() {
    if (this.refCount <= 0 || this.socket) return;
    const wsBase = environment.apiBaseUrl.replace(/^http/, 'ws');
    this.socket = new WebSocket(`${wsBase}/api/ws/odds`);

    this.socket.onopen = () => {
      this.retryDelay = 1000;
    };
    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'odds_update') this.oddsSubject.next(data);
      } catch {}
    };
    this.socket.onerror = () => {};
    this.socket.onclose = () => {
      this.socket = null;
      if (this.refCount > 0) {
        this.retryTimer = setTimeout(() => this.reconnect(), this.retryDelay);
        this.retryDelay = Math.min(this.retryDelay * 2, this.maxRetryDelay);
      }
    };
  }

  disconnect() {
    this.refCount = Math.max(0, this.refCount - 1);
    if (this.refCount > 0) return; // still in use by other consumers

    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer);
      this.retryTimer = null;
    }
    if (this.socket) {
      this.socket.onclose = null; // prevent auto-reconnect loop
      this.socket.close();
      this.socket = null;
    }
    this.retryDelay = 1000;
  }
}
