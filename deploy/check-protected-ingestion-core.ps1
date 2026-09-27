param(
    [string]$BaseRef = "HEAD~1",
    [switch]$AllowCoreChange
)

$ErrorActionPreference = "Stop"

$repoRoot = (
    git rev-parse --show-toplevel
).Trim()

if (-not $repoRoot) {
    throw "Unable to determine Git repository root."
}

$manifestPath = Join-Path `
    $repoRoot `
    "workers\insyt_processing_worker\protected_core_v1.txt"

if (-not (Test-Path $manifestPath)) {
    throw "Protected-core manifest missing: $manifestPath"
}

$protected = Get-Content $manifestPath |
    ForEach-Object {
        $_.Trim().Replace("\", "/")
    } |
    Where-Object {
        $_ -and -not $_.StartsWith("#")
    }

$changed = git diff `
    --name-only `
    "$BaseRef...HEAD" |
    ForEach-Object {
        $_.Trim().Replace("\", "/")
    } |
    Where-Object {
        $_
    }

$violations = @()

foreach ($file in $changed) {
    if ($protected -contains $file) {
        $violations += $file
    }
}

if ($violations.Count -eq 0) {
    Write-Host "PASS: Protected INSYT ingestion core unchanged."
    exit 0
}

Write-Host ""
Write-Host "PROTECTED INSYT INGESTION CORE CHANGED:"
Write-Host ""

foreach ($file in $violations) {
    Write-Host "  $file"
}

Write-Host ""

if (-not $AllowCoreChange) {
    Write-Host "FAIL: Core v1 files cannot change during ordinary feature/adapter work."
    Write-Host ""
    Write-Host "New file formats must use:"
    Write-Host "  workers/insyt_processing_worker/apc/adapters/"
    Write-Host "  workers/insyt_processing_worker/apc/routing/file_type_registry.py"
    Write-Host ""
    Write-Host "An intentional core change requires the protected regression suite."
    exit 1
}

Write-Host "WARNING: Explicit protected-core change authorized."
exit 0