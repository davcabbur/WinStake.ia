import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

// ── Dashboard Models ──

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

// ── Analysis Models ──

export interface ValueBet {
  match: string;
  commence_time: string;
  selection: string;
  odds: number;
  ev_percent: number;
  probability: number;
  kelly_half: number;
  stake_units: number;
  confidence: string;
}

export interface AnalysisResponse {
  status: string;
  value_bets: ValueBet[];
  total_analyzed: number;
}

export interface AnalysisResult {
  home_team: string;
  away_team: string;
  commence_time: string;
  prob_home: number;
  prob_draw: number;
  prob_away: number;
  prob_over25: number;
  prob_under25: number;
  odds_home: number;
  odds_draw: number;
  odds_away: number;
  recommendation: string;
  confidence: string;
  selection: string | null;
  ev_percent: number | null;
  stake_units: number | null;
  run_date: string;
}

export interface SelectionStats {
  selection: string;
  total: number;
  wins: number;
  profit: number;
  staked: number;
  avg_ev: number;
}

import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class ApiService {
  private http = inject(HttpClient);
  private baseUrl = environment.apiBaseUrl;

  // ── Dashboard endpoints ──

  getStats(): Observable<DashboardStats> {
    return this.http.get<DashboardStats>(`${this.baseUrl}/api/dashboard/stats`);
  }

  getHistory(limit: number = 50, offset: number = 0): Observable<{ data: BetHistory[], limit: number, offset: number }> {
    return this.http.get<{ data: BetHistory[], limit: number, offset: number }>(
      `${this.baseUrl}/api/dashboard/history?limit=${limit}&offset=${offset}`
    );
  }

  getChartData(): Observable<ChartData> {
    return this.http.get<ChartData>(`${this.baseUrl}/api/dashboard/chart-data`);
  }

  getAnalysisResults(): Observable<{ results: AnalysisResult[], total: number }> {
    return this.http.get<{ results: AnalysisResult[], total: number }>(
      `${this.baseUrl}/api/dashboard/analysis-results`
    );
  }

  getStatsBySelection(): Observable<{ breakdown: SelectionStats[] }> {
    return this.http.get<{ breakdown: SelectionStats[] }>(
      `${this.baseUrl}/api/dashboard/stats-by-selection`
    );
  }

  // ── Analysis engine endpoint ──

  runAnalysis(): Observable<AnalysisResponse> {
    return this.http.get<AnalysisResponse>(`${this.baseUrl}/api/v1/analysis/`);
  }
}
