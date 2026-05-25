param(
    [switch]$CreateVenv
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($CreateVenv) {
    if (!(Test-Path ".\.venv\Scripts\python.exe")) {
        py -3 -m venv .venv
    }
    $python = ".\.venv\Scripts\python.exe"
} elseif (Test-Path ".\.venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
} else {
    $python = "python"
}

& $python -m pip install --upgrade pip
& $python -m pip install -r .\requirements.txt
& $python -m pip install -r .\vendor\flowkit\requirements.txt

if (!(Test-Path ".\config.json")) {
    Copy-Item ".\config.example.json" ".\config.json"
}

New-Item -ItemType Directory -Force .\outputs, .\refs, .\state, .\logs | Out-Null

Write-Host "Setup complete."
Write-Host "Next: .\start_agent.ps1"
Write-Host "Then: .\open_flow_chrome.ps1"
