import { Component } from '@angular/core';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  template: `
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-icon">WS</div>
        <span>WinStake.ia</span>
      </div>
      
      <nav class="nav-menu">
        <a href="#" class="nav-item active">
          💡 Dashboard
        </a>
        <a href="#" class="nav-item">
          📊 Histórico
        </a>
        <a href="#" class="nav-item">
          ⚡ En Directo
        </a>
        <a href="#" class="nav-item">
          ⚙️ Ajustes
        </a>
      </nav>
      
      <div class="sidebar-footer">
        <div class="status-indicator">
          <span class="dot pulse"></span>
          <span>Motor Activo</span>
        </div>
      </div>
    </aside>
  `,
  styles: [`
    .sidebar {
      width: 260px;
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
      gap: 8px;
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
    
    .sidebar-footer {
      padding: 24px;
      border-top: 1px solid var(--border-color);
    }
    
    .status-indicator {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 14px;
      color: var(--text-secondary);
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
export class SidebarComponent {}
