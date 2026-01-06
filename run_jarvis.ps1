Param(
    [string]$Script = "jarvisbot.py",
    [ValidateSet("Realtime","High","AboveNormal","Normal","BelowNormal","Idle")]
    [string]$Priority = "High"
)

$venvCreated = $false

if (-not (Test-Path -Path ".\venv")) {
    Write-Host 'Creating virtual environment...'
    python -m venv venv
    $venvCreated = $true
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

if ($venvCreated) {
    Write-Host 'Installing dependencies into venv...'
    & .\venv\Scripts\python.exe -m pip install --upgrade pip
    & .\venv\Scripts\python.exe -m pip install -r requirements.txt
}

# Determine python executable: prefer venv python when available
if (Test-Path .\venv\Scripts\python.exe) {
    $pythonExe = Join-Path -Path '.' -ChildPath 'venv\Scripts\python.exe'
} else {
    $pythonExe = 'python'
}

Write-Host ("Starting script: {0} with priority {1}" -f $Script, $Priority)

# Start process and set priority class
$proc = Start-Process -FilePath $pythonExe -ArgumentList $Script -WorkingDirectory (Get-Location) -PassThru
$proc.PriorityClass = $Priority


# Notes: Prefer High or AboveNormal. Avoid Realtime unless you know what you're doing.
