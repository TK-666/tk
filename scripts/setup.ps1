param(
    [string]$PythonPath,
    [switch]$SkipDatabase
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $projectRoot 'backend'
$frontend = Join-Path $projectRoot 'frontend'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable exited with code $LASTEXITCODE."
    }
}

$npm = (Get-Command npm.cmd -ErrorAction Stop).Source
$nodeVersionText = Invoke-Checked -Executable 'node.exe' -Arguments @('--version')
$nodeVersion = [version]($nodeVersionText.TrimStart('v'))
if (!(($nodeVersion.Major -eq 20 -and $nodeVersion -ge [version]'20.19.0') -or
      $nodeVersion -ge [version]'22.12.0')) {
    throw 'Install Node.js 20.19+ in the 20.x series, or 22.12+.'
}

$pythonCheck = "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 'Python 3.11+ is required')"
if (!(Test-Path -LiteralPath $venvPython)) {
    $pythonArgs = @()
    if (!$PythonPath) {
        $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
        if ($launcher) {
            $PythonPath = $launcher.Source
            $pythonArgs = @('-3')
        } else {
            $PythonPath = (Get-Command python.exe -ErrorAction Stop).Source
        }
    }
    Invoke-Checked -Executable $PythonPath -Arguments ($pythonArgs + @('-c', $pythonCheck))
    Invoke-Checked -Executable $PythonPath -Arguments ($pythonArgs + @('-m', 'venv', (Join-Path $backend '.venv')))
}

Invoke-Checked -Executable $venvPython -Arguments @('-c', $pythonCheck)
Invoke-Checked -Executable $venvPython -Arguments @('-m', 'pip', 'install', '-r', (Join-Path $backend 'requirements.txt'))

Push-Location -LiteralPath $frontend
try {
    Invoke-Checked -Executable $npm -Arguments @('ci')
} finally {
    Pop-Location
}

$envPath = Join-Path $projectRoot '.env'
if (!(Test-Path -LiteralPath $envPath)) {
    $secret = Invoke-Checked -Executable $venvPython -Arguments @('-c', 'import secrets; print(secrets.token_hex(32))')
    $template = Get-Content -LiteralPath (Join-Path $projectRoot '.env.example') -Raw
    $settings = $template -replace '(?m)^SECRET_KEY=', "SECRET_KEY=$secret"
    New-Item -Path $envPath -ItemType File -Value $settings | Out-Null
}

if (!$SkipDatabase) {
    Push-Location -LiteralPath $backend
    try {
        Invoke-Checked -Executable $venvPython -Arguments @('-m', 'flask', '--app', 'run', 'init-db')
    } finally {
        Pop-Location
    }
}

Write-Host 'Setup complete. In two terminals run scripts/dev.ps1 Backend and scripts/dev.ps1 Frontend.'
