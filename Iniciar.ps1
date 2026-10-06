param([switch]$AbrirNavegador)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$appUrl = 'http://127.0.0.1:8765'

function Test-AppReady {
    try {
        $health = Invoke-RestMethod -Uri ($appUrl + '/api/health') -TimeoutSec 1
        return ($health.status -eq 'ok' -and $health.schema -eq 1)
    } catch { return $false }
}

Write-Output 'Abrindo COMBIO - Avanco PipeRack OSBL...'
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$pythonPath = if (Test-Path -LiteralPath $venvPython) { $venvPython } elseif (Test-Path -LiteralPath $bundledPython) { $bundledPython } else { (Get-Command python).Source }
$runScript = Join-Path $projectRoot 'tools\run.py'
New-Item -ItemType Directory -Force -Path (Join-Path $projectRoot 'data') | Out-Null
$runningWorker = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains($runScript) -and $_.CommandLine -match '\bworker\b' } |
    Select-Object -First 1
if (-not $runningWorker) {
    Start-Process -FilePath $pythonPath -ArgumentList @('"'+$runScript+'"','worker') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'data\worker.log') -RedirectStandardError (Join-Path $projectRoot 'data\worker-error.log')
}
if (-not (Test-AppReady)) {
    Start-Process -FilePath $pythonPath -ArgumentList @('"'+$runScript+'"','api') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'data\api.log') -RedirectStandardError (Join-Path $projectRoot 'data\api-error.log')
}
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    if (Test-AppReady) { $ready = $true; break }
    Start-Sleep -Milliseconds 400
}
if (-not $ready) {
    throw 'Nao foi possivel iniciar o aplicativo. Confira data\api-error.log na pasta do projeto.'
}
if ($AbrirNavegador) {
    # User-facing browser launch: the shortcut explicitly requests this window.
    Start-Process $appUrl
}
Write-Output ('Aplicativo pronto: ' + $appUrl)
