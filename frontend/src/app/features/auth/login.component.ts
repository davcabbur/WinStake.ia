import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="login-container" style="display:flex; justify-content:center; align-items:center; height:100vh; background:#121212; color:white;">
      <div style="background:#1e1e1e; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.5);">
        <h2 style="color: #00d2ff;">WinStake.ia</h2>
        <p>Inicia sesión de forma segura.</p>
        <button 
          (click)="fakeLogin()"
          style="width: 100%; padding: 10px; background: #00d2ff; color:#000; font-weight:bold; border:none; border-radius:4px; cursor:pointer;"
        >
          Demo Login (FastAPI)
        </button>
      </div>
    </div>
  `,
  styles: []
})
export class LoginComponent {
  constructor(private auth: AuthService, private router: Router) {}

  fakeLogin() {
    // Aquí iría la llamada HTTP al backend FastAPI (/api/v1/auth/login)
    this.auth.login('dummy_jwt_token_for_phase_2');
    this.router.navigate(['/dashboard']);
  }
}
