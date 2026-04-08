// ============================================================
// WinStake.ia — PM2 Process Manager Configuration
// ============================================================
// Instalar PM2: npm install -g pm2 pm2-windows-startup
// Iniciar todo: pm2 start ecosystem.config.js
// Guardar estado: pm2 save
// Auto-arranque: pm2-startup install
// Ver estado: pm2 status
// Ver logs: pm2 logs
// ============================================================

const path = require('path');
const projectDir = __dirname;
const pythonExe = path.join(projectDir, 'venv', 'Scripts', 'python.exe');

module.exports = {
  apps: [
    {
      name: 'winstake-api',
      script: pythonExe,
      args: 'run_api.py',
      cwd: projectDir,
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONUTF8: '1',
      },
      log_file: path.join(projectDir, 'logs', 'api.log'),
      error_file: path.join(projectDir, 'logs', 'api.error.log'),
      time: true,
    },
    {
      name: 'winstake-bot',
      script: pythonExe,
      args: path.join('src', 'bot_daemon.py'),
      cwd: projectDir,
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env: {
        PYTHONUNBUFFERED: '1',
        PYTHONUTF8: '1',
      },
      log_file: path.join(projectDir, 'logs', 'bot.log'),
      error_file: path.join(projectDir, 'logs', 'bot.error.log'),
      time: true,
    },
    {
      name: 'winstake-frontend',
      script: 'cmd',
      args: '/c npm start',
      cwd: path.join(projectDir, 'frontend'),
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',
      log_file: path.join(projectDir, 'logs', 'frontend.log'),
      error_file: path.join(projectDir, 'logs', 'frontend.error.log'),
      time: true,
    },
  ],
};
