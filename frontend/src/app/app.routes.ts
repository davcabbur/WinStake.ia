import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent)
  },
  {
    path: 'analysis',
    loadComponent: () => import('./features/analysis/analysis.component').then(m => m.AnalysisComponent)
  },
  {
    path: 'history',
    loadComponent: () => import('./features/history/history.component').then(m => m.HistoryComponent)
  },
  {
    path: 'live',
    loadComponent: () => import('./features/live/live.component').then(m => m.LiveComponent)
  },
  {
    path: 'settings',
    loadComponent: () => import('./features/settings/settings.component').then(m => m.SettingsComponent)
  },
  {
    path: '**',
    redirectTo: ''
  }
];
