param(
    [string]$Prompt = "科技风拉满的宏观未来城市核心场景，电影级光影，超细节，真实质感",
    [int]$Count = 1
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = "python"
if (Test-Path ".\.venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
}

& $python .\flow.py generate $Prompt --count $Count --aspect-ratio landscape --download --prefix demo
