import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div style="padding: 2rem; color: #fff;">
      <h2>Dashboard de Apuestas</h2>
      <p>Bienvenido. Aquí verás las cuotas en vivo y las "Value Bets" encontradas por el algoritmo.</p>
      
      <div style="margin-top:20px; padding:15px; border-left: 4px solid #00d2ff; background: #1e1e1e;">
        <strong>Buscando oportunidades en FastAPI...</strong> (Demo)
      </div>
    </div>
  `,
  styles: []
})
export class DashboardComponent {}
