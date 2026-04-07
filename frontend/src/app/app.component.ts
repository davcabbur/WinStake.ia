import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { SidebarComponent } from './core/components/sidebar/sidebar.component';
import { TopbarComponent } from './core/components/topbar/topbar.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, SidebarComponent, TopbarComponent],
  template: `
    <div class="app-layout">
      <app-sidebar></app-sidebar>
      <div class="app-main">
        <app-topbar></app-topbar>
        <div class="app-content">
          <router-outlet></router-outlet>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .app-layout {
      display: flex;
      height: 100vh;
      overflow: hidden;
    }
    .app-main {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
    }
    .app-content {
      padding: 0 40px 40px 40px;
      max-width: 1400px;
      flex: 1;
    }
    @media (max-width: 768px) {
      .app-content {
        padding: 0 16px 24px 16px;
      }
    }
  `]
})
export class AppComponent {}
