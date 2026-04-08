# ============================================================
# WinStake.ia — Setup PM2 Auto-Start
# ============================================================
# Configura PM2 para gestionar todos los servicios y
# levantarlos automáticamente al arrancar Windows.
#
# Ejecutar una sola vez como Administrador:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_pm2.ps1
# ============================================================

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  WinStake.ia — Setup PM2" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Crear carpeta de logs
$LogsDir = Join-Path $ProjectDir "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir | Out-Null
    Write-Host "Carpeta logs/ creada" -ForegroundColor Green
}

# 2. Instalar PM2 y pm2-windows-startup globalmente
Write-Host "Instalando PM2..." -ForegroundColor Yellow
npm install -g pm2 pm2-windows-startup
if ($LASTEXITCODE -ne 0) { Write-Error "Fallo al instalar PM2"; exit 1 }
Write-Host "PM2 instalado" -ForegroundColor Green

# 3. Arrancar todos los servicios
Write-Host ""
Write-Host "Arrancando servicios..." -ForegroundColor Yellow
Set-Location $ProjectDir
pm2 start ecosystem.config.js
if ($LASTEXITCODE -ne 0) { Write-Error "Fallo al arrancar servicios"; exit 1 }

# 4. Guardar estado actual
Write-Host "Guardando estado PM2..." -ForegroundColor Yellow
pm2 save

# 5. Configurar arranque automático en Windows
Write-Host "Configurando arranque automático..." -ForegroundColor Yellow
pm2-startup install

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Listo! Servicios activos:" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
pm2 status
Write-Host ""
Write-Host "Comandos utiles:" -ForegroundColor Cyan
Write-Host "  pm2 status          — ver estado de todos los servicios"
Write-Host "  pm2 logs            — ver logs en tiempo real"
Write-Host "  pm2 logs winstake-api  — logs solo del backend"
Write-Host "  pm2 restart all     — reiniciar todo"
Write-Host "  pm2 stop all        — parar todo"
Write-Host ""
Write-Host "URLs disponibles:" -ForegroundColor Cyan
Write-Host "  Frontend:  http://localhost:4200"
Write-Host "  API:       http://localhost:8000"
Write-Host "  API docs:  http://localhost:8000/docs"
Write-Host ""
