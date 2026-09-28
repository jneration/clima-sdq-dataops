# Registra la carga incremental diaria (6:00 a.m.) en el Programador de tareas de Windows.
# No requiere administrador: la tarea corre con tu usuario y solo con la sesión iniciada.
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\registrar_tarea.ps1
$ErrorActionPreference = 'Stop'

$nombre  = 'ClimaSDQ-Incremental'
$raiz    = Split-Path -Parent $PSScriptRoot
$python  = 'C:\venvs\clima\Scripts\python.exe'
$script  = Join-Path $raiz 'src\pipeline.py'

if (-not (Test-Path $python)) { throw "No existe $python. Complete el Paso 0." }

$accion = New-ScheduledTaskAction -Execute $python `
    -Argument "`"$script`" incremental" -WorkingDirectory $raiz
$disparador = New-ScheduledTaskTrigger -Daily -At '06:00'
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $nombre -Action $accion -Trigger $disparador `
    -Settings $config -Principal $principal `
    -Description 'Pipeline DataOps de clima de Santo Domingo: carga incremental diaria' -Force | Out-Null

Get-ScheduledTask -TaskName $nombre | Get-ScheduledTaskInfo |
    Select-Object @{n='Tarea';e={$nombre}}, NextRunTime, LastTaskResult | Format-List
