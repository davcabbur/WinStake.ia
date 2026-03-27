import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { AuthService } from '../auth/auth.service';

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [CommonModule, RouterModule],
  template: `
    <div style="min-height: 100vh; background: #121212; display:flex; flex-direction:column;">
      <nav style="padding: 1rem; background: #0a0a0a; color: #00d2ff; display:flex; justify-content:space-between; align-items:center;">
        <h1 style="margin:0;">WinStake.ia</h1>
        <button (click)="logout()" style="background:transparent; color:#fff; border:1px solid #444; padding:5px 10px; cursor:pointer;">Cerrar Sesión</button>
      </nav>
      <main style="flex:1;">
        <router-outlet></router-outlet>
      </main>
    </div>
  `,
  styles: []
})
export class MainLayoutComponent {
  constructor(private auth: AuthService) {}

  logout() {
    this.auth.logout();
    window.location.reload(); // Quick reset for demo
  }
}
