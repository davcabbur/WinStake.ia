import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { CommonModule } from '@angular/common';
import { TickerStripComponent } from './core/components/ticker-strip/ticker-strip.component';
import { TerminalHeaderComponent } from './core/components/terminal-header/terminal-header.component';
import { StatusLineComponent } from './core/components/status-line/status-line.component';
import { AuthService } from './core/auth/auth.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, CommonModule, TickerStripComponent, TerminalHeaderComponent, StatusLineComponent],
  template: `
    <ng-container *ngIf="auth.currentUser(); else bare">
      <div class="term-shell">
        <app-ticker-strip></app-ticker-strip>
        <app-terminal-header></app-terminal-header>
        <main class="term-outlet">
          <router-outlet></router-outlet>
        </main>
        <app-status-line></app-status-line>
      </div>
    </ng-container>
    <ng-template #bare>
      <router-outlet></router-outlet>
    </ng-template>
  `,
  styles: [`
    .term-shell {
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background: var(--ws-bg);
      /* Desktop-first 1440px (handoff §5). Centrado sobre el fondo del documento. */
      max-width: 1440px;
      margin: 0 auto;
    }
    .term-outlet {
      flex: 1;
    }
  `]
})
export class AppComponent {
  constructor(public auth: AuthService) {}
}
