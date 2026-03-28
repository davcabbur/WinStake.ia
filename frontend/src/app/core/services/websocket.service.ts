import { Injectable } from '@angular/core';
import { Subject, Observable } from 'rxjs';

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

@Injectable({
  providedIn: 'root'
})
export class WebsocketService {
  private socket: WebSocket | null = null;
  private oddsSubject = new Subject<OddsUpdate>();
  
  public odds$: Observable<OddsUpdate> = this.oddsSubject.asObservable();

  connect() {
    if (this.socket) {
      return;
    }

    this.socket = new WebSocket('ws://localhost:8000/api/ws/odds');

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

    this.socket.onclose = () => {
      console.log('WS Connection closed, retrying in 5s...');
      this.socket = null;
      setTimeout(() => this.connect(), 5000);
    };
  }

  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }
}
