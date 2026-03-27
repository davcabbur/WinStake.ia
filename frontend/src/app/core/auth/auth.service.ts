import { Injectable, signal } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class AuthService {
  // Estado reactivo simple para demostración
  currentUser = signal<{ username: string } | null>(null);

  constructor() {
    this.checkToken();
  }

  checkToken() {
    const token = localStorage.getItem('access_token');
    if (token) {
      // Decode JWT safely or assume valid if exists (demo)
      this.currentUser.set({ username: 'Jugador' });
    } else {
      this.currentUser.set(null);
    }
  }

  login(token: string) {
    localStorage.setItem('access_token', token);
    this.checkToken();
  }

  logout() {
    localStorage.removeItem('access_token');
    this.currentUser.set(null);
  }

  isAuthenticated(): boolean {
    return !!localStorage.getItem('access_token');
  }
}
