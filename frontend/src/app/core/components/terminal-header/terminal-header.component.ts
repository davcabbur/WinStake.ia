import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterModule } from '@angular/router';
import { WebsocketService } from '../../services/websocket.service';

interface FKey { key: string; label: string; route: string; }

/**
 * Header terminal (handoff §7.2). Reemplaza al sidebar+topbar previos.
 * Logo: el emblema original (winstake-logo.jpeg) — decisión del manager de usar
 * el JPEG tal cual en lugar de la reconstrucción SVG que sugería el handoff.
 * Wordmark, tabs F1–F5 como router-links, y bloque de estado (ENGINE / WS·API·TG / USER).
 */
@Component({
  selector: 'app-terminal-header',
  standalone: true,
  imports: [CommonModule, RouterModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="hdr">
      <div class="left">
        <!-- Logo — emblema vectorial NBA (balón + gráfico de valor, sin marca de agua) -->
        <div class="logo">
          <svg viewBox="0 0 100 100" width="100%" height="100%" role="img" aria-label="WinStake.ia">
            <defs>
              <linearGradient id="wsGold" x1="0" x2="1" y1="0" y2="1">
                <stop offset="0%" stop-color="#ffe9b0"/>
                <stop offset="48%" stop-color="#ffb020"/>
                <stop offset="100%" stop-color="#9c6a0c"/>
              </linearGradient>
              <linearGradient id="wsGoldBar" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stop-color="#ffe9b0"/>
                <stop offset="100%" stop-color="#d99513"/>
              </linearGradient>
              <radialGradient id="wsNavy" cx="35%" cy="28%" r="85%">
                <stop offset="0%" stop-color="#1f4fcf"/>
                <stop offset="55%" stop-color="#0a3aa5"/>
                <stop offset="100%" stop-color="#04164f"/>
              </radialGradient>
              <radialGradient id="wsBall" cx="36%" cy="30%" r="78%">
                <stop offset="0%" stop-color="#ffbf7a"/>
                <stop offset="60%" stop-color="#ef7a26"/>
                <stop offset="100%" stop-color="#c2540f"/>
              </radialGradient>
            </defs>

            <!-- Disco + anillo dorado biselado (contorno del icono) -->
            <circle cx="50" cy="50" r="48.5" fill="url(#wsNavy)"/>
            <circle cx="50" cy="50" r="48.5" fill="none" stroke="url(#wsGold)" stroke-width="4"/>
            <circle cx="50" cy="50" r="45"   fill="none" stroke="#5a3c08" stroke-width="1" opacity="0.8"/>
            <circle cx="50" cy="50" r="42.5" fill="none" stroke="url(#wsGold)" stroke-width="1.2" opacity="0.7"/>
            <!-- brillo superior -->
            <path d="M16,36 A40,40 0 0 1 84,36" fill="none" stroke="#ffffff" stroke-width="2" opacity="0.10"/>

            <!-- Balón de baloncesto -->
            <g stroke="#6e2f0c" stroke-width="0.9" fill="none" stroke-linecap="round">
              <circle cx="36" cy="33" r="10" fill="url(#wsBall)"/>
              <line x1="36" y1="23" x2="36" y2="43"/>
              <line x1="26" y1="33" x2="46" y2="33"/>
              <path d="M28.5,24.5 Q36,33 28.5,41.5"/>
              <path d="M43.5,24.5 Q36,33 43.5,41.5"/>
            </g>

            <!-- Gráfico de barras ascendente + flecha de valor -->
            <g>
              <rect x="55" y="35" width="5" height="9"  fill="url(#wsGoldBar)"/>
              <rect x="62" y="31" width="5" height="13" fill="url(#wsGoldBar)"/>
              <rect x="69" y="26" width="5" height="18" fill="url(#wsGoldBar)"/>
              <rect x="76" y="21" width="5" height="23" fill="url(#wsGoldBar)"/>
              <polyline points="55,38 64,32 71,28 82,18" fill="none" stroke="url(#wsGold)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
              <path d="M82,18 l-7,0.5 l3.5,4.8 z" fill="url(#wsGold)"/>
            </g>

            <!-- Wordmark + subtítulo NBA -->
            <text x="50" y="60" text-anchor="middle" fill="url(#wsGold)"
                  font-family="'Inter', sans-serif" font-size="11.5" font-weight="800"
                  letter-spacing="-0.5">WINSTAKE<tspan fill="#ffd97a">.IA</tspan></text>
            <text x="50" y="70.5" text-anchor="middle" fill="#ffce6e"
                  font-family="'JetBrains Mono', monospace" font-size="4.8" font-weight="700"
                  letter-spacing="1.1">IA DE APUESTAS · NBA</text>
            <text x="50" y="83" text-anchor="middle" fill="url(#wsGold)" font-size="7" letter-spacing="2">★★★</text>
          </svg>
        </div>

        <!-- Wordmark -->
        <div class="brand">
          <div class="wordmark">WINSTAKE<span class="ia">.IA</span><span class="ver">TERMINAL v2.4.0</span></div>
          <div class="tagline">Sistema cuantitativo · Moneyball approach</div>
        </div>

        <!-- Nav F1–F5 -->
        <nav class="tabs">
          <a *ngFor="let f of fkeys"
             class="tab"
             [routerLink]="f.route"
             routerLinkActive="on"
             [routerLinkActiveOptions]="{ exact: f.route === '/' }">
            <span class="fk">{{ f.key }}</span>{{ f.label }}
          </a>
        </nav>
      </div>

      <!-- Estado -->
      <div class="right">
        <div class="engine">
          <span class="dot" [class.live]="engineActive()"></span>
          <span class="lbl">ENGINE</span>
          <span class="state" [class.active]="engineActive()">{{ engineActive() ? 'ACTIVE' : 'IDLE' }}</span>
        </div>
        <div class="conn">
          WS <span [class.ok]="connected()" [class.off]="!connected()">●</span>
          API <span class="ok">●</span>
          TG <span class="warn">●</span>
        </div>
        <div class="user"><span class="ulbl">USER</span>WS-001</div>
      </div>
    </header>
  `,
  styles: [`
    .hdr {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 20px;
      border-bottom: 1px solid var(--ws-line2);
      background: var(--ws-bg);
    }
    .left { display: flex; align-items: center; gap: 14px; }

    .logo {
      width: 50px; height: 50px; border-radius: 50%;
      box-shadow: var(--ws-amber-glow);
      display: flex; align-items: center; justify-content: center; flex: none;
    }
    .logo svg { display: block; }

    .wordmark { font-weight: 700; font-size: var(--ws-text-title); letter-spacing: .06em; }
    .ia  { color: var(--ws-amber); }
    .ver { color: var(--ws-dim); font-weight: 400; font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); margin-left: 8px; }
    .tagline { font-size: var(--ws-text-meta); color: var(--ws-dim); font-family: var(--ws-font-mono); }

    .tabs { display: flex; margin-left: 32px; font-family: var(--ws-font-mono); font-size: var(--ws-text-body); }
    .tab {
      padding: 6px 14px;
      border-right: 1px solid var(--ws-line);
      border-top: 2px solid transparent;
      color: var(--ws-dim);
      font-weight: 500;
      text-decoration: none;
      cursor: pointer;
      transition: color .15s, background .15s;
    }
    .tab:hover { color: var(--ws-text); }
    .tab.on {
      background: var(--ws-amber-bg);
      color: var(--ws-amber);
      font-weight: 700;
      border-top: 2px solid var(--ws-amber);
    }
    .fk { color: var(--ws-dim2); margin-right: 6px; font-size: var(--ws-text-kicker); }

    .right { display: flex; align-items: center; gap: 16px; font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); }
    .engine { display: flex; align-items: center; gap: 6px; }
    .engine .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--ws-dim2); }
    .engine .dot.live { background: var(--ws-win); box-shadow: 0 0 6px var(--ws-win); animation: ws-pulse 1.5s ease-in-out infinite; color: var(--ws-win); }
    .engine .lbl { color: var(--ws-dim); }
    .engine .state { color: var(--ws-dim); font-weight: 700; }
    .engine .state.active { color: var(--ws-win); }

    .conn { color: var(--ws-dim); }
    .conn .ok   { color: var(--ws-win); }
    .conn .warn { color: var(--ws-amber); }
    .conn .off  { color: var(--ws-dim2); }

    .user { border: 1px solid var(--ws-line2); padding: 6px 12px; color: var(--ws-text); font-weight: 700; font-size: var(--ws-text-cell); }
    .ulbl { color: var(--ws-dim); font-size: var(--ws-text-kicker); margin-right: 8px; }
  `]
})
export class TerminalHeaderComponent {
  private readonly ws = inject(WebsocketService);

  readonly fkeys: FKey[] = [
    { key: 'F1', label: 'DASHBOARD', route: '/' },
    { key: 'F2', label: 'ANALYSIS',  route: '/analysis' },
    { key: 'F3', label: 'HISTORY',   route: '/history' },
    { key: 'F4', label: 'LIVE ODDS', route: '/live' },
    { key: 'F5', label: 'SETTINGS',  route: '/settings' },
  ];

  readonly connected = this.ws.connected;
  // Motor "activo" = WS conectado. El backend no expone un heartbeat del engine,
  // así que usamos la conexión del WS como proxy honesto.
  readonly engineActive = this.ws.connected;
}
