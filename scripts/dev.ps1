param(
    [Parameter(Mandatory)]
    [ValidateSet('Backend', 'Frontend')]
    [string]$Service,
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 5000,
    [ValidateRange(1, 65535)]
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

if ($Service -eq 'Backend') {
    $backend = Join-Path $projectRoot 'backend'
    $python = Join-Path $backend '.venv\Scripts\python.exe'
    if (!(Test-Path -LiteralPath $python)) {
        throw 'Run scripts/setup.ps1 first.'
    }
    Push-Location -LiteralPath $backend
    try {
        & $python -m flask --app run run --debug --host 127.0.0.1 --port $BackendPort
        if ($LASTEXITCODE -ne 0) { throw "Flask exited with code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
} else {
    $frontend = Join-Path $projectRoot 'frontend'
    if (!(Test-Path -LiteralPath (Join-Path $frontend 'node_modules\.bin\vite.cmd'))) {
        throw 'Run scripts/setup.ps1 first.'
    }
    $previousTarget = $env:API_PROXY_TARGET
    Push-Location -LiteralPath $frontend
    try {
        $env:API_PROXY_TARGET = "http://127.0.0.1:$BackendPort"
        & npm.cmd run dev -- --port $FrontendPort --strictPort
        if ($LASTEXITCODE -ne 0) { throw "Vite exited with code $LASTEXITCODE." }
    } finally {
        $env:API_PROXY_TARGET = $previousTarget
        Pop-Location
    }
}
