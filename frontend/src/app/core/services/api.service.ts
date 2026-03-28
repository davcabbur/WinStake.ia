import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface DashboardStats {
  total_bets: number;
  won_bets: number;
  win_rate: number;
  total_profit: number;
}

export interface BetHistory {
  run_date: string;
  home_team: string;
  away_team: string;
  commence_time: string;
  selection: string;
  odds: number;
  ev_percent: number;
  confidence: string;
  stake_units: number;
  bet_won: number;
  profit_units: number;
}

export interface ChartData {
  dates: string[];
  cumulative_profit: number[];
}

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private http = inject(HttpClient);
  private baseUrl = 'http://localhost:8000/api/dashboard';

  getStats(): Observable<DashboardStats> {
    return this.http.get<DashboardStats>(`${this.baseUrl}/stats`);
  }

  getHistory(limit: number = 50, offset: number = 0): Observable<{data: BetHistory[], limit: number, offset: number}> {
    return this.http.get<{data: BetHistory[], limit: number, offset: number}>(`${this.baseUrl}/history?limit=${limit}&offset=${offset}`);
  }

  getChartData(): Observable<ChartData> {
    return this.http.get<ChartData>(`${this.baseUrl}/chart-data`);
  }
}
