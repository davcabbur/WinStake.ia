import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';

interface NavItem {
  icon: string;
  label: string;
  route: string;
}

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, RouterModule],
  template: `
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-icon">WS</div>
        <span>WinStake.ia</span>
      </div>

      <nav class="nav-menu">
        @for (item of navItems; track item.route) {
          <a [routerLink]="item.route"
             routerLinkActive="active"
             [routerLinkActiveOptions]="{ exact: item.route === '/' }"
             class="nav-item">
            <span class="nav-icon">{{ item.icon }}</span>
            {{ item.label }}
          </a>
        }
      </nav>

      <div class="sidebar-footer">
        <div class="status-indicator">
          <span class="dot pulse"></span>
          <span>Motor Activo</span>
        </div>
        <div class="version">v1.0.0</div>
      </div>
    </aside>
  `,
  styles: [`
    .sidebar {
      width: 260px;
      min-width: 260px;
      background: var(--bg-surface);
      border-right: 1px solid var(--border-color);
      display: flex;
      flex-direction: column;
      height: 100vh;
    }

    .logo {
      padding: 24px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 20px;
      font-weight: 700;
      color: var(--text-primary);
    }

    .logo-icon {
      background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      font-weight: 800;
    }

    .nav-menu {
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      flex: 1;
    }

    .nav-item {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      border-radius: 10px;
      color: var(--text-secondary);
      text-decoration: none;
      font-weight: 500;
      font-size: 14px;
      transition: all 0.2s ease;
    }

    .nav-item:hover {
      background: var(--bg-surface-hover);
      color: var(--text-primary);
    }

    .nav-item.active {
      background: rgba(59, 130, 246, 0.1);
      color: var(--accent-primary);
    }

    .nav-icon {
      font-size: 18px;
      width: 24px;
      text-align: center;
    }

    .sidebar-footer {
      padding: 20px 24px;
      border-top: 1px solid var(--border-color);
    }

    .status-indicator {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--text-secondary);
    }

    .version {
      margin-top: 8px;
      font-size: 11px;
      color: var(--text-secondary);
      opacity: 0.5;
    }

    .dot {
      width: 8px;
      height: 8px;
      background: var(--status-success-text);
      border-radius: 50%;
    }

    .dot.pulse {
      box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4);
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.4); }
      70% { box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
      100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
    }
  `]
})
export class SidebarComponent {
  navItems: NavItem[] = [
    { icon: '\u{1F4CA}', label: 'Dashboard', route: '/' },
    { icon: '\u{1F3AF}', label: 'Analisis', route: '/analysis' },
    { icon: '\u{1F4C8}', label: 'Historico', route: '/history' },
    { icon: '\u26A1',     label: 'En Directo', route: '/live' },
    { icon: '\u2699\uFE0F', label: 'Ajustes', route: '/settings' },
  ];
}
