Param(
    [string]$Script = "jarvisbot.py"
)

if (-not (Test-Path -Path ".\venv")) {
    Write-Host 'Creating virtual environment...'
    python -m venv venv
}

$policy = Get-ExecutionPolicy -Scope Process -ErrorAction SilentlyContinue
if (-not $policy) { $policy = Get-ExecutionPolicy }
if ($policy -eq 'Restricted') {
    Write-Host 'ExecutionPolicy is Restricted — using Bypass for this process.'
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
}

$activatePs = Join-Path -Path '.' -ChildPath 'venv\Scripts\Activate.ps1'
$activateBat = Join-Path -Path '.' -ChildPath 'venv\Scripts\activate.bat'
if (Test-Path $activatePs) {
    Write-Host 'Activating venv (PowerShell)...'
    & $activatePs
} elseif (Test-Path $activateBat) {
    Write-Host 'Activating venv (cmd)...'
    & $activateBat
} else {
    Write-Host 'Activation script not found; continuing without activation.'
}

Write-Host ("Running script: {0}" -f $Script)
python $Script
