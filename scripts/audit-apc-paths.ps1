param(
    [string]$Repo = "C:\INSYT_SAAS",
    [string]$ApiBase = "https://api.insyt360.com",
    [string]$Workspace = "capture",
    [string]$Client = "Client1",
    [string]$Project = "Project_Client1",
    [string]$ProjectDisplay = "Project Client1"
)

$ErrorActionPreference = "Continue"

function Section([string]$Title) {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host $Title
    Write-Host "============================================================"
}

function Clean-Segment([string]$Value) {
    if ($null -eq $Value) { $Value = "" }
    return ([string]$Value).Trim().Trim("/").Replace("\", "/")
}

function Storage-Key([string]$Value) {
    return (Clean-Segment $Value).Replace(" ", "_")
}

function Enc([string]$Value) {
    return [System.Uri]::EscapeDataString($Value)
}

function Get-NestedValue($Object, [string]$Path) {
    if ($null -eq $Object -or [string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }

    $cur = $Object

    foreach ($part in $Path.Split(".")) {
        if ($null -eq $cur) {
            return $null
        }

        $prop = $cur.PSObject.Properties[$part]

        if ($null -eq $prop) {
            return $null
        }

        $cur = $prop.Value
    }

    return $cur
}

function Invoke-JsonGet([string]$Url) {
    try {
        return Invoke-RestMethod `
            -Method GET `
            -Uri $Url `
            -Headers @{ accept = "application/json" }
    }
    catch {
        $statusCode = $null

        try {
            $statusCode = [int]$_.Exception.Response.StatusCode
        }
        catch {}

        return [pscustomobject]@{
            __error = $_.Exception.Message
            status_code = $statusCode
            url = $Url
        }
    }
}

function New-PathCheck(
    [string]$Name,
    [string]$Value,
    [string]$ExpectedBase,
    [string]$BadWorkspaceFirst,
    [string]$BadSpaceBase
) {
    $status = "MISSING"

    if ($Value) {
        if ($Value -like "$ExpectedBase*") {
            $status = "PASS"
        }
        elseif ($Value -like "$BadWorkspaceFirst*") {
            $status = "FAIL_WORKSPACE_FIRST_ORDER"
        }
        elseif ($Value -like "$BadSpaceBase*") {
            $status = "FAIL_PROJECT_SPACE_NOT_STORAGE_KEY"
        }
        elseif ($Value -match "processing_center|source/processing_center|source/native|source/text") {
            $status = "FAIL_OTHER_APC_PATH_MISMATCH"
        }
        else {
            $status = "WARN_NOT_APC_PATH"
        }
    }

    return [pscustomobject]@{
        Name = $Name
        Status = $status
        Value = $Value
        ExpectedPrefix = $ExpectedBase
        BadWorkspaceFirstPrefix = $BadWorkspaceFirst
        BadSpacePrefix = $BadSpaceBase
    }
}

$ApiBase = $ApiBase.TrimEnd("/")
$WorkspaceKey = (Clean-Segment $Workspace).ToLower()
$ClientKey = Clean-Segment $Client
$ProjectStorageKey = Storage-Key $ProjectDisplay
$ProjectParamStorageKey = Storage-Key $Project

$ExpectedBase = "$ClientKey/$WorkspaceKey/$ProjectStorageKey"
$ExpectedBaseFromProjectParam = "$ClientKey/$WorkspaceKey/$ProjectParamStorageKey"
$BadWorkspaceFirst = "$WorkspaceKey/$ClientKey/$ProjectStorageKey"
$BadWorkspaceFirstFromProjectParam = "$WorkspaceKey/$ClientKey/$ProjectParamStorageKey"
$BadSpaceBase = "$ClientKey/$WorkspaceKey/$(Clean-Segment $ProjectDisplay)"

$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$OutDir = Join-Path $Repo "apc-path-audit-$Stamp"
New-Item -ItemType Directory -Force $OutDir | Out-Null

Section "Expected canonical APC path"

Write-Host "Repo:                         $Repo"
Write-Host "API:                          $ApiBase"
Write-Host "Workspace:                    $WorkspaceKey"
Write-Host "Client:                       $ClientKey"
Write-Host "ProjectDisplay:               $ProjectDisplay"
Write-Host "ProjectStorageKey:            $ProjectStorageKey"
Write-Host "ExpectedBase:                 $ExpectedBase"
Write-Host "ExpectedBaseFromProjectParam: $ExpectedBaseFromProjectParam"
Write-Host "BadWorkspaceFirst:            $BadWorkspaceFirst"
Write-Host "BadSpaceBase:                 $BadSpaceBase"
Write-Host "OutputDir:                    $OutDir"

# --------------------------------------------------------------------
# 1. Local code scan
# --------------------------------------------------------------------

Section "1. Local code scan for inconsistent APC path construction"

$ScanRoots = @(
    (Join-Path $Repo "backend")
    (Join-Path $Repo "workers")
) | Where-Object { Test-Path $_ }

$SkipRegex = "\\(\.git|node_modules|dist|build|\.next|\.venv|venv|__pycache__|\.pytest_cache)\\"
$Files = foreach ($root in $ScanRoots) {
    Get-ChildItem -Path $root -Recurse -File -Include *.py |
        Where-Object { $_.FullName -notmatch $SkipRegex }
}

$Checks = @(
    [pscustomobject]@{
        Severity = "FAIL"
        Issue = "Workspace-first literal/order: {workspace}/{client}/{project}"
        Regex = "\{workspace\}/\{client\}/\{project\}"
    },
    [pscustomobject]@{
        Severity = "FAIL"
        Issue = "Workspace-first text: workspace/client/project"
        Regex = "workspace/client/project"
    },
    [pscustomobject]@{
        Severity = "FAIL"
        Issue = "Direct runtime path construction: routing.workspace/routing.client/routing.project"
        Regex = "routing\.workspace.*routing\.client.*routing\.project"
    },
    [pscustomobject]@{
        Severity = "FAIL"
        Issue = "Hard-coded live bad workspace-first sample"
        Regex = "capture/Client1/Project_Client1|capture/Client1/Project Client1"
    },
    [pscustomobject]@{
        Severity = "FAIL"
        Issue = "Storage helper preserves project spaces"
        Regex = "project_name\s*=\s*clean_path_part\(project\)"
    },
    [pscustomobject]@{
        Severity = "REVIEW"
        Issue = "Direct APC uploads path literal"
        Regex = "source/processing_center/uploads"
    },
    [pscustomobject]@{
        Severity = "REVIEW"
        Issue = "Direct APC jobs/staged/reports/archive path literal"
        Regex = "processing_center/(jobs|staged|reports|archive|removed|work|temp|telemetry)"
    },
    [pscustomobject]@{
        Severity = "REVIEW"
        Issue = "Storage normalization helper"
        Regex = "storage_project_key|storage_segment|build_project_storage_key|clean_segment|clean_path_part"
    }
)

$Findings = New-Object System.Collections.Generic.List[object]

foreach ($file in $Files) {
    try {
        $lines = Get-Content -LiteralPath $file.FullName

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = [string]$lines[$i]

            foreach ($check in $Checks) {
                if ($line -match $check.Regex) {
                    $Findings.Add([pscustomobject]@{
                        Severity = $check.Severity
                        Issue = $check.Issue
                        File = $file.FullName.Replace($Repo, "").TrimStart("\")
                        Line = $i + 1
                        Text = $line.Trim()
                    })
                }
            }
        }
    }
    catch {
        $Findings.Add([pscustomobject]@{
            Severity = "ERROR"
            Issue = "Could not scan file"
            File = $file.FullName.Replace($Repo, "").TrimStart("\")
            Line = 0
            Text = $_.Exception.Message
        })
    }
}

$FindingsPath = Join-Path $OutDir "local-code-scan.csv"
$Findings | Export-Csv -NoTypeInformation -Path $FindingsPath

$FailFindings = @($Findings | Where-Object { $_.Severity -eq "FAIL" })
$ReviewFindings = @($Findings | Where-Object { $_.Severity -eq "REVIEW" })

Write-Host "FAIL findings:   $($FailFindings.Count)"
Write-Host "REVIEW findings: $($ReviewFindings.Count)"
Write-Host "CSV:             $FindingsPath"

if ($FailFindings.Count -gt 0) {
    $FailFindings | Format-Table Severity, Issue, File, Line, Text -AutoSize
}

# --------------------------------------------------------------------
# 2. Local route extraction
# --------------------------------------------------------------------

Section "2. Local Processing Center route table from backend/app/api/*.py"

$RouteRows = New-Object System.Collections.Generic.List[object]
$ApiDir = Join-Path $Repo "backend\app\api"

if (Test-Path $ApiDir) {
    $ApiFiles = Get-ChildItem -Path $ApiDir -Filter "*.py" -Recurse

    foreach ($file in $ApiFiles) {
        $lines = Get-Content -LiteralPath $file.FullName

        for ($i = 0; $i -lt $lines.Count; $i++) {
            $line = [string]$lines[$i]

            if ($line -match '^\s*@router\.(get|post|put|patch|delete)\(\s*"([^"]+)"') {
                $method = $matches[1].ToUpper()
                $path = $matches[2]
                $func = ""

                for ($j = $i + 1; $j -lt [Math]::Min($lines.Count, $i + 30); $j++) {
                    if ([string]$lines[$j] -match '^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)') {
                        $func = $matches[1]
                        break
                    }

                    if ([string]$lines[$j] -match '^\s*async\s+def\s+([A-Za-z_][A-Za-z0-9_]*)') {
                        $func = $matches[1]
                        break
                    }
                }

                if ($path -match "processing-center") {
                    $RouteRows.Add([pscustomobject]@{
                        Method = $method
                        Path = $path
                        Function = $func
                        File = $file.FullName.Replace($Repo, "").TrimStart("\")
                        Line = $i + 1
                    })
                }
            }
        }
    }
}

$RoutesPath = Join-Path $OutDir "local-processing-center-routes.csv"
$RouteRows | Sort-Object Path, Method | Export-Csv -NoTypeInformation -Path $RoutesPath
$RouteRows | Sort-Object Path, Method | Format-Table Method, Path, Function, File, Line -AutoSize
Write-Host "CSV: $RoutesPath"

# --------------------------------------------------------------------
# 3. Local Python runtime helper probe
# --------------------------------------------------------------------

Section "3. Local Python runtime path helper probe"

$ProbePy = Join-Path $OutDir "local_runtime_probe.py"
$ProbeJson = Join-Path $OutDir "local-runtime-probe.json"
$BackendPath = Join-Path $Repo "backend"

@"
import json
import sys
import traceback

sys.path.insert(0, r"$BackendPath")

result = {}

def safe(name, fn):
    try:
        result[name] = fn()
    except Exception as exc:
        result[name] = {
            "error": type(exc).__name__ + ": " + str(exc),
            "traceback": traceback.format_exc(),
        }

def probe_azure_layout():
    from apc.azure_layout import AzureRoutingConfig

    out = {}

    for project in ["Project Client1", "Project_Client1"]:
        r = AzureRoutingConfig.from_args(
            workspace="capture",
            client="Client1",
            project=project,
            azure_write=True,
        )

        out[project] = {
            "prefix": r.prefix,
            "uploads": r.processing_paths().get("uploads"),
            "jobs": r.processing_paths().get("jobs"),
            "native": r.review_paths().get("native"),
            "text": r.review_paths().get("text"),
            "reports": r.review_paths().get("reports"),
        }

    return out

def probe_processing_center_azure():
    from app.api.processing_center_azure import _project_base_path, _storage_project_key

    out = {}

    for project in ["Project Client1", "Project_Client1"]:
        out[project] = {
            "storage_project_key": _storage_project_key(project),
            "project_base_path": _project_base_path(
                workspace="capture",
                client="Client1",
                project=project,
            ),
        }

    return out

def probe_storage_paths():
    from app.services.storage_paths import build_project_base_path

    out = {}

    for project in ["Project Client1", "Project_Client1"]:
        out[project] = build_project_base_path(
            workspace="capture",
            client="Client1",
            project=project,
        )

    return out

safe("apc.azure_layout.AzureRoutingConfig", probe_azure_layout)
safe("app.api.processing_center_azure._project_base_path", probe_processing_center_azure)
safe("app.services.storage_paths.build_project_base_path", probe_storage_paths)

print(json.dumps(result, indent=2))
"@ | Set-Content -Path $ProbePy -Encoding UTF8

$oldPyPath = $env:PYTHONPATH
$env:PYTHONPATH = $BackendPath

try {
    $probeOutput = & python $ProbePy 2>&1
    $probeOutput | Set-Content -Path $ProbeJson -Encoding UTF8
    Write-Host $probeOutput
    Write-Host "JSON: $ProbeJson"
}
finally {
    $env:PYTHONPATH = $oldPyPath
}

# --------------------------------------------------------------------
# 4. Live OpenAPI route table
# --------------------------------------------------------------------

Section "4. Live OpenAPI Processing Center routes"

$LiveRoutes = New-Object System.Collections.Generic.List[object]
$OpenApi = Invoke-JsonGet "$ApiBase/openapi.json"

if ($OpenApi.__error) {
    Write-Host "OpenAPI fetch failed: $($OpenApi.__error)"
}
else {
    foreach ($p in $OpenApi.paths.PSObject.Properties) {
        if ($p.Name -match "processing-center") {
            $methods = @($p.Value.PSObject.Properties.Name)

            $LiveRoutes.Add([pscustomobject]@{
                Path = $p.Name
                Methods = ($methods -join ",")
            })
        }
    }

    $LiveRoutesPath = Join-Path $OutDir "live-processing-center-routes.csv"
    $LiveRoutes | Sort-Object Path | Export-Csv -NoTypeInformation -Path $LiveRoutesPath
    $LiveRoutes | Sort-Object Path | Format-Table Path, Methods -AutoSize
    Write-Host "CSV: $LiveRoutesPath"

    $RequiredRoutes = @(
        [pscustomobject]@{
            Suffix = "/{workspace}/processing-center/uploads/remove"
            Method = "post"
        },
        [pscustomobject]@{
            Suffix = "/{workspace}/processing-center/tracked-jobs/start"
            Method = "post"
        },
        [pscustomobject]@{
            Suffix = "/{workspace}/processing-center/uploads"
            Method = "get"
        },
        [pscustomobject]@{
            Suffix = "/{workspace}/processing-center/job-history"
            Method = "get"
        }
    )

    $RouteChecks = New-Object System.Collections.Generic.List[object]

    foreach ($req in $RequiredRoutes) {
        $matchesForPath = @($LiveRoutes | Where-Object { $_.Path -like "*$($req.Suffix)" })
        $hasMethod = $false

        foreach ($m in $matchesForPath) {
            $methodList = @($m.Methods.Split(",") | ForEach-Object { $_.Trim().ToLower() })

            if ($methodList -contains $req.Method.ToLower()) {
                $hasMethod = $true
            }
        }

        $RouteChecks.Add([pscustomobject]@{
            Status = if ($hasMethod) { "PASS" } else { "FAIL_ROUTE_OR_METHOD_MISSING" }
            RequiredSuffix = $req.Suffix
            RequiredMethod = $req.Method
            MatchingPaths = (($matchesForPath | ForEach-Object { "$($_.Path) [$($_.Methods)]" }) -join " ; ")
        })
    }

    $RouteChecksPath = Join-Path $OutDir "live-required-route-checks.csv"
    $RouteChecks | Export-Csv -NoTypeInformation -Path $RouteChecksPath
    $RouteChecks | Format-Table Status, RequiredMethod, RequiredSuffix, MatchingPaths -AutoSize
    Write-Host "CSV: $RouteChecksPath"
}

# --------------------------------------------------------------------
# 5. Live API and worker path probes
# --------------------------------------------------------------------

Section "5. Live API and worker path probes"

$ClientQ = Enc $Client
$ProjectQ = Enc $Project
$ProjectDisplayQ = Enc $ProjectDisplay

$UploadsDisplayUrl = "$ApiBase/api/$WorkspaceKey/processing-center/uploads?client=$ClientQ&project=$ProjectDisplayQ"
$UploadsProjectUrl = "$ApiBase/api/$WorkspaceKey/processing-center/uploads?client=$ClientQ&project=$ProjectQ"
$HistoryUrl = "$ApiBase/api/$WorkspaceKey/processing-center/job-history?client=$ClientQ&project=$ProjectQ"

$UploadsDisplay = Invoke-JsonGet $UploadsDisplayUrl
$UploadsProject = Invoke-JsonGet $UploadsProjectUrl
$History = Invoke-JsonGet $HistoryUrl

$LatestJob = $null
$TrackedStatus = $null
$TrackedStatusUrl = $null

if (-not $History.__error -and $History.jobs) {
    $LatestJob = @($History.jobs) |
        Sort-Object `
            @{ Expression = { $_.completed_at }; Descending = $true },
            @{ Expression = { $_.last_modified }; Descending = $true },
            @{ Expression = { $_.created_at }; Descending = $true } |
        Select-Object -First 1

    if ($LatestJob -and $LatestJob.job_id) {
        $JobIdQ = Enc $LatestJob.job_id
        $TrackedStatusUrl = "$ApiBase/api/$WorkspaceKey/processing-center/tracked-jobs/$JobIdQ/status?client=$ClientQ&project=$ProjectQ"
        $TrackedStatus = Invoke-JsonGet $TrackedStatusUrl
    }
}

$PathChecks = New-Object System.Collections.Generic.List[object]

$PathChecks.Add((New-PathCheck `
    -Name "GET uploads with display project uploads_prefix" `
    -Value (Get-NestedValue $UploadsDisplay "uploads_prefix") `
    -ExpectedBase $ExpectedBase `
    -BadWorkspaceFirst $BadWorkspaceFirst `
    -BadSpaceBase $BadSpaceBase))

$PathChecks.Add((New-PathCheck `
    -Name "GET uploads with storage project uploads_prefix" `
    -Value (Get-NestedValue $UploadsProject "uploads_prefix") `
    -ExpectedBase $ExpectedBaseFromProjectParam `
    -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
    -BadSpaceBase $BadSpaceBase))

$PathChecks.Add((New-PathCheck `
    -Name "GET job-history jobs_prefix" `
    -Value (Get-NestedValue $History "jobs_prefix") `
    -ExpectedBase $ExpectedBaseFromProjectParam `
    -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
    -BadSpaceBase $BadSpaceBase))

if ($TrackedStatus) {
    $PathChecks.Add((New-PathCheck `
        -Name "Tracked worker routing.processing.paths.uploads" `
        -Value (Get-NestedValue $TrackedStatus "routing.processing.paths.uploads") `
        -ExpectedBase $ExpectedBaseFromProjectParam `
        -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
        -BadSpaceBase $BadSpaceBase))

    $PathChecks.Add((New-PathCheck `
        -Name "Tracked worker routing.processing.paths.jobs" `
        -Value (Get-NestedValue $TrackedStatus "routing.processing.paths.jobs") `
        -ExpectedBase $ExpectedBaseFromProjectParam `
        -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
        -BadSpaceBase $BadSpaceBase))

    $PathChecks.Add((New-PathCheck `
        -Name "Tracked worker routing.review_outputs.paths.native" `
        -Value (Get-NestedValue $TrackedStatus "routing.review_outputs.paths.native") `
        -ExpectedBase $ExpectedBaseFromProjectParam `
        -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
        -BadSpaceBase $BadSpaceBase))

    $PathChecks.Add((New-PathCheck `
        -Name "Tracked worker routing.review_outputs.paths.text" `
        -Value (Get-NestedValue $TrackedStatus "routing.review_outputs.paths.text") `
        -ExpectedBase $ExpectedBaseFromProjectParam `
        -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
        -BadSpaceBase $BadSpaceBase))

    $PathChecks.Add((New-PathCheck `
        -Name "Tracked worker routing.review_outputs.paths.reports" `
        -Value (Get-NestedValue $TrackedStatus "routing.review_outputs.paths.reports") `
        -ExpectedBase $ExpectedBaseFromProjectParam `
        -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
        -BadSpaceBase $BadSpaceBase))

    $PathChecks.Add((New-PathCheck `
        -Name "Tracked worker archive_upload.source_prefix" `
        -Value (Get-NestedValue $TrackedStatus "archive_upload.source_prefix") `
        -ExpectedBase $ExpectedBaseFromProjectParam `
        -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
        -BadSpaceBase $BadSpaceBase))

    $PathChecks.Add((New-PathCheck `
        -Name "Tracked worker archive_upload.archive_prefix" `
        -Value (Get-NestedValue $TrackedStatus "archive_upload.archive_prefix") `
        -ExpectedBase $ExpectedBaseFromProjectParam `
        -BadWorkspaceFirst $BadWorkspaceFirstFromProjectParam `
        -BadSpaceBase $BadSpaceBase))
}

$LiveProbePayload = [ordered]@{
    expected = [ordered]@{
        expected_base_display = $ExpectedBase
        expected_base_project_param = $ExpectedBaseFromProjectParam
        bad_workspace_first_display = $BadWorkspaceFirst
        bad_workspace_first_project_param = $BadWorkspaceFirstFromProjectParam
        bad_space_base = $BadSpaceBase
    }
    urls = [ordered]@{
        uploads_display = $UploadsDisplayUrl
        uploads_project = $UploadsProjectUrl
        history = $HistoryUrl
        tracked_status = $TrackedStatusUrl
    }
    uploads_display = $UploadsDisplay
    uploads_project = $UploadsProject
    history_latest_job = $LatestJob
    tracked_status = $TrackedStatus
    path_checks = $PathChecks
}

$LiveProbePath = Join-Path $OutDir "live-path-probes.json"
$LiveProbePayload | ConvertTo-Json -Depth 100 | Set-Content -Path $LiveProbePath -Encoding UTF8

$PathChecksPath = Join-Path $OutDir "live-path-checks.csv"
$PathChecks | Export-Csv -NoTypeInformation -Path $PathChecksPath
$PathChecks | Format-Table Name, Status, Value, ExpectedPrefix -AutoSize
Write-Host "CSV:  $PathChecksPath"
Write-Host "JSON: $LiveProbePath"

# --------------------------------------------------------------------
# 6. Summary
# --------------------------------------------------------------------

Section "6. Summary"

$LiveFailures = @($PathChecks | Where-Object { $_.Status -like "FAIL*" })
$LocalFailures = @($Findings | Where-Object { $_.Severity -eq "FAIL" })
$RouteFailures = @($RouteChecks | Where-Object { $_.Status -like "FAIL*" })

Write-Host "Local code FAIL findings: $($LocalFailures.Count)"
Write-Host "Live path FAIL findings:  $($LiveFailures.Count)"
Write-Host "Live route FAIL findings: $($RouteFailures.Count)"
Write-Host "Output directory:         $OutDir"

if ($LocalFailures.Count -gt 0) {
    Write-Host ""
    Write-Host "LOCAL CODE FAILURES:"
    $LocalFailures | Format-Table Issue, File, Line, Text -AutoSize
}

if ($RouteFailures.Count -gt 0) {
    Write-Host ""
    Write-Host "LIVE ROUTE FAILURES:"
    $RouteFailures | Format-Table Status, RequiredMethod, RequiredSuffix, MatchingPaths -AutoSize
}

if ($LiveFailures.Count -gt 0) {
    Write-Host ""
    Write-Host "LIVE PATH FAILURES:"
    $LiveFailures | Format-Table Name, Status, Value, ExpectedPrefix -AutoSize
}

Write-Host ""
Write-Host "Files generated:"
Get-ChildItem $OutDir | ForEach-Object {
    Write-Host " - $($_.FullName)"
}

if ($LiveFailures.Count -gt 0 -or $LocalFailures.Count -gt 0 -or $RouteFailures.Count -gt 0) {
    exit 2
}

exit 0
