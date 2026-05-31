import { ChangeDetectionStrategy, Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { BotCommandVM } from '../../dashboard.models';

/**
 * Telegram Bot footer (handoff §7.11). Lista mono de comandos recientes.
 * HANDOFF-DEVIATION: datos mock — no hay endpoint del log del bot.
 */
@Component({
  selector: 'app-telegram-footer',
  standalone: true,
  imports: [CommonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="panel">
      <div class="kicker">TELEGRAM BOT · &#64;winstake_bot</div>
      <div class="cmds">
        <div *ngFor="let c of commands">→ {{ c.cmd }} <span class="dim">{{ c.time }} · {{ c.detail }}</span></div>
        <div *ngIf="commands.length === 0" class="empty">Sin actividad reciente del bot</div>
      </div>
    </div>
  `,
  styles: [`
    .panel { background: var(--ws-panel); padding: 14px 18px; border-top: 1px solid var(--ws-line2); }
    .kicker { font-family: var(--ws-font-mono); font-size: var(--ws-text-kicker); color: var(--ws-dim); letter-spacing: var(--ws-ls-kicker); margin-bottom: 6px; }
    .cmds { font-family: var(--ws-font-mono); font-size: var(--ws-text-meta); color: var(--ws-text); line-height: 1.7; }
    .dim { color: var(--ws-dim); }
    .empty { color: var(--ws-dim2); font-style: italic; }
  `]
})
export class TelegramFooterComponent {
  @Input() commands: BotCommandVM[] = [];
}
