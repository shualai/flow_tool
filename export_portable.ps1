param(
    [string]$OutputZip = "",
    [switch]$IncludeOutputs,
    [switch]$IncludeChromeProfile,
    [switch]$PublicRelease
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $PSScriptRoot).Path
if (-not $OutputZip) {
    $zipName = if ($PublicRelease) { "flow_api_tool_public.zip" } else { "flow_api_tool_portable.zip" }
    $OutputZip = Join-Path (Split-Path -Parent $root) $zipName
}
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "flow_api_tool_export_$stamp"
$packageRoot = Join-Path $tempRoot "flow_api_tool"

function Copy-FileSafe {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    $parent = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-TreeSafe {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDir,
        [Parameter(Mandatory = $true)][string]$DestinationDir,
        [string[]]$ExcludeRelative = @()
    )
    if (-not (Test-Path -LiteralPath $SourceDir)) {
        return
    }

    $sourceResolved = (Resolve-Path $SourceDir).Path
    $sourcePrefixLength = $sourceResolved.TrimEnd("\").Length + 1
    Get-ChildItem -LiteralPath $sourceResolved -Recurse -Force -File | ForEach-Object {
        $rel = $_.FullName.Substring($sourcePrefixLength)
        $relNorm = $rel -replace "\\", "/"
        $skip = $false
        foreach ($pattern in $ExcludeRelative) {
            if ($relNorm -like $pattern) {
                $skip = $true
                break
            }
        }
        if ($skip) {
            return
        }
        Copy-FileSafe -Source $_.FullName -Destination (Join-Path $DestinationDir $rel)
    }
}

if (Test-Path -LiteralPath $tempRoot) {
    $resolvedTemp = (Resolve-Path $tempRoot).Path
    $systemTemp = ([System.IO.Path]::GetTempPath()).TrimEnd("\")
    if (-not $resolvedTemp.StartsWith($systemTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove unexpected temp path: $resolvedTemp"
    }
    Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $packageRoot | Out-Null

$rootFiles = @(
    ".gitignore",
    "config.example.json",
    "flow.py",
    "generate_example.ps1",
    "LICENSE",
    "OPEN_SOURCE_CHECKLIST.md",
    "open_flow_chrome.ps1",
    "README.md",
    "requirements.txt",
    "SECURITY.md",
    "setup.ps1",
    "start_agent.ps1"
)
if (-not $PublicRelease) {
    $rootFiles += "config.json"
}

foreach ($file in $rootFiles) {
    $source = Join-Path $root $file
    if (Test-Path -LiteralPath $source) {
        Copy-FileSafe -Source $source -Destination (Join-Path $packageRoot $file)
    }
}

Copy-TreeSafe -SourceDir (Join-Path $root "src") -DestinationDir (Join-Path $packageRoot "src") -ExcludeRelative @("__pycache__/*", "*.pyc")
Copy-TreeSafe -SourceDir (Join-Path $root "examples") -DestinationDir (Join-Path $packageRoot "examples") -ExcludeRelative @("__pycache__/*", "*.pyc")
if ($PublicRelease) {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "refs") | Out-Null
    Copy-FileSafe -Source (Join-Path $root "refs\.gitkeep") -Destination (Join-Path $packageRoot "refs\.gitkeep")
} else {
    Copy-TreeSafe -SourceDir (Join-Path $root "refs") -DestinationDir (Join-Path $packageRoot "refs")
}

$stateDest = Join-Path $packageRoot "state"
New-Item -ItemType Directory -Force -Path $stateDest | Out-Null
if ($PublicRelease) {
    Copy-FileSafe -Source (Join-Path $root "state\.gitkeep") -Destination (Join-Path $stateDest ".gitkeep")
} else {
    foreach ($file in @("flow_tool.sqlite", "refs.json", "runs.jsonl")) {
        $source = Join-Path (Join-Path $root "state") $file
        if (Test-Path -LiteralPath $source) {
            Copy-FileSafe -Source $source -Destination (Join-Path $stateDest $file)
        }
    }
}

$vendorExcludes = @(
    ".git/*",
    "__pycache__/*",
    "*/__pycache__/*",
    "*.pyc",
    "*/flow_agent.db",
    "*/flow_agent.db-shm",
    "*/flow_agent.db-wal",
    "output/*"
)
Copy-TreeSafe -SourceDir (Join-Path $root "vendor") -DestinationDir (Join-Path $packageRoot "vendor") -ExcludeRelative $vendorExcludes

if ($PublicRelease) {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "outputs") | Out-Null
    Copy-FileSafe -Source (Join-Path $root "outputs\.gitkeep") -Destination (Join-Path $packageRoot "outputs\.gitkeep")
} elseif ($IncludeOutputs) {
    Copy-TreeSafe -SourceDir (Join-Path $root "outputs") -DestinationDir (Join-Path $packageRoot "outputs")
} else {
    New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "outputs") | Out-Null
}

if ($IncludeChromeProfile -and -not $PublicRelease) {
    Copy-TreeSafe -SourceDir (Join-Path $root "chrome-profile") -DestinationDir (Join-Path $packageRoot "chrome-profile") -ExcludeRelative @("*/Cache/*", "*/Code Cache/*", "*/GPUCache/*")
}

New-Item -ItemType Directory -Force -Path (Join-Path $packageRoot "logs") | Out-Null

@"
Flow API Tool portable export
CreatedAt: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Source: $root

Mode: $(if ($PublicRelease) { "PublicRelease" } else { "PortablePrivate" })

Excluded by default:
- logs/*.log
- vendor/flowkit/flow_agent.db*
- chrome-profile
- outputs, unless -IncludeOutputs is used
- temporary reverse-engineering files under state/

PublicRelease also excludes:
- config.json
- state/flow_tool.sqlite
- state/refs.json
- state/runs.jsonl
- refs/*

After extracting:
1. Run .\setup.ps1
2. Check config.json
3. Run .\start_agent.ps1
4. Run .\open_flow_chrome.ps1 and log in to Flow
"@ | Set-Content -Path (Join-Path $packageRoot "EXPORT_NOTES.txt") -Encoding UTF8

$zipParent = Split-Path -Parent $OutputZip
if ($zipParent) {
    New-Item -ItemType Directory -Force -Path $zipParent | Out-Null
}

Compress-Archive -LiteralPath $packageRoot -DestinationPath $OutputZip -Force

$zip = Get-Item -LiteralPath $OutputZip
Write-Host "Created: $($zip.FullName)"
Write-Host "SizeMB: $([Math]::Round($zip.Length / 1MB, 2))"
Write-Host "Temp: $tempRoot"
