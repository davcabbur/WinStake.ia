# ============================================================
# WinStake.ia — Configurar Windows Task Scheduler
# ============================================================
# Crea tareas programadas para ejecutar el análisis automáticamente.
# Ejecutar como Administrador:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows_task.ps1
# ============================================================

$ErrorActionPreference = "Stop"

# ── Configuración ──────────────────────────────────────────
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$PythonExe = Join-Path $ProjectDir "venv\Scripts\python.exe"
$SchedulerScript = Join-Path $ProjectDir "scheduler.py"
$TaskNamePrefix = "WinStake.ia"

# Verificar que existen los archivos necesarios
if (-not (Test-Path $PythonExe)) {
    Write-Error "No se encontró Python en: $PythonExe"
    Write-Host "Ejecuta primero: python -m venv venv && venv\Scripts\pip install -r requirements.txt"
    exit 1
}

if (-not (Test-Path $SchedulerScript)) {
    Write-Error "No se encontró scheduler.py en: $SchedulerScript"
    exit 1
}

# ── Definir horarios ───────────────────────────────────────
$Schedules = @(
    @{ Day = "Friday";    Time = "10:00"; Desc = "Análisis pre-jornada viernes" },
    @{ Day = "Saturday";  Time = "09:00"; Desc = "Análisis pre-jornada sábado" },
    @{ Day = "Sunday";    Time = "09:00"; Desc = "Análisis pre-jornada domingo" },
    @{ Day = "Tuesday";   Time = "10:00"; Desc = "Análisis jornada entre semana (martes)" },
    @{ Day = "Wednesday"; Time = "10:00"; Desc = "Análisis jornada entre semana (miércoles)" }
)

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  WinStake.ia — Setup Task Scheduler" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Proyecto: $ProjectDir"
Write-Host "Python:   $PythonExe"
Write-Host ""

# ── Crear tareas ───────────────────────────────────────────

foreach ($sched in $Schedules) {
    $taskName = "$TaskNamePrefix - $($sched.Day)"
    $dayOfWeek = $sched.Day

    Write-Host "Creando tarea: $taskName" -ForegroundColor Yellow

    # Eliminar tarea existente si hay
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "  → Tarea anterior eliminada" -ForegroundColor DarkGray
    }

    # Acción: ejecutar scheduler.py --once
    $action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "--utf8 `"$SchedulerScript`" --once" `
        -WorkingDirectory $ProjectDir

    # Trigger: día de la semana a la hora configurada
    $timeParts = $sched.Time.Split(":")
    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek $dayOfWeek `
        -At "$($sched.Time)"

    # Settings
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -RunOnlyIfNetworkAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

    # Registrar tarea
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $sched.Desc `
        -RunLevel Limited

    Write-Host "  ✅ $($sched.Day) a las $($sched.Time)" -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  ✅ $($Schedules.Count) tareas creadas" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Para ver las tareas:" -ForegroundColor Cyan
Write-Host "  Get-ScheduledTask | Where-Object {`$_.TaskName -like 'WinStake*'}"
Write-Host ""
Write-Host "Para eliminar todas:" -ForegroundColor Cyan
Write-Host "  Get-ScheduledTask | Where-Object {`$_.TaskName -like 'WinStake*'} | Unregister-ScheduledTask"
Write-Host ""
