[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Task,

    [ValidateSet(1, 2)]
    [int]$ReviewPass = 1,

    [string]$Model = "",

    [string]$CodexPath = "",

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ReviewDir = Join-Path $ProjectRoot ".review"
$HandoffPath = Join-Path $ReviewDir "handoff.md"
$ReviewPath = Join-Path $ReviewDir "codex-review.md"
$PassOnePath = Join-Path $ReviewDir "codex-review-pass1.md"

function Resolve-CodexExecutable {
    param([string]$ExplicitPath)

    $candidates = [System.Collections.Generic.List[string]]::new()
    if (-not [string]::IsNullOrWhiteSpace($ExplicitPath)) {
        $candidates.Add($ExplicitPath)
    }
    if (-not [string]::IsNullOrWhiteSpace($env:CODEX_CLI_PATH)) {
        $candidates.Add($env:CODEX_CLI_PATH)
    }

    $pathCommand = Get-Command codex -ErrorAction SilentlyContinue
    if ($pathCommand) {
        $candidates.Add($pathCommand.Source)
    }

    # The Codex VS Code extension bundles codex.exe, but sandboxed tool calls do
    # not always inherit VS Code's augmented PATH. Discover the bundle without
    # hardcoding an extension version or a user name.
    # Sandboxes can virtualize GetFolderPath(UserProfile) while preserving the
    # host USERPROFILE/APPDATA values. Probe all non-empty candidates.
    $profileCandidates = @(
        $env:USERPROFILE,
        "$($env:HOMEDRIVE)$($env:HOMEPATH)",
        ([Environment]::GetFolderPath("UserProfile")),
        $(if ($env:APPDATA) { Split-Path -Parent (Split-Path -Parent $env:APPDATA) })
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
    $extensionRoots = [System.Collections.Generic.List[string]]::new()
    foreach ($profile in $profileCandidates) {
        $extensionRoots.Add((Join-Path $profile ".vscode\extensions"))
        $extensionRoots.Add((Join-Path $profile ".vscode-insiders\extensions"))
        $extensionRoots.Add((Join-Path $profile ".cursor\extensions"))
    }
    foreach ($root in $extensionRoots) {
        if (-not (Test-Path $root)) { continue }
        $extensions = @(
            Get-ChildItem -LiteralPath $root -Directory -Filter "openai.chatgpt-*-win32-x64" `
                -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTime -Descending
        )
        foreach ($extension in $extensions) {
            $candidates.Add(
                (Join-Path $extension.FullName "bin\windows-x86_64\codex.exe")
            )
        }
    }

    foreach ($candidate in $candidates) {
        if ([string]::IsNullOrWhiteSpace($candidate)) { continue }
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw @"
Codex CLI was not found. Resolution order: -CodexPath, CODEX_CLI_PATH, PATH,
then VS Code/VS Code Insiders/Cursor extension bundles. If Codex works in another
terminal, pass its absolute executable path with -CodexPath or expose it through
CODEX_CLI_PATH in the Claude tool environment.
"@
}

if (-not (Test-Path $HandoffPath)) {
    throw ".review/handoff.md is missing. Run scripts/prepare_review.ps1 and complete the semantic sections first."
}

$handoff = [System.IO.File]::ReadAllText($HandoffPath)
$expectedMode = if ($ReviewPass -eq 1) { "DISCOVERY" } else { "CLOSURE_ONLY" }
if ($handoff -notmatch "Review pass:\s*``$ReviewPass/2``") {
    throw ".review/handoff.md is not prepared for review pass $ReviewPass/2."
}
if ($handoff -notmatch "Review mode:\s*``$expectedMode``") {
    throw ".review/handoff.md does not declare review mode $expectedMode."
}
if ($handoff -match "- \[ \] Complete before requesting review\.") {
    throw ".review/handoff.md still contains the placeholder acceptance criterion. Complete it before review."
}

if ($ReviewPass -eq 2 -and -not (Test-Path $PassOnePath)) {
    throw ".review/codex-review-pass1.md is missing; pass 2 cannot verify closure without the pass-1 report."
}

$codexExecutable = Resolve-CodexExecutable $CodexPath

if ($ReviewPass -eq 1) {
    $prompt = @"
This is review pass 1 of 2 -- DISCOVERY for: $Task

Read AGENTS.md, CLAUDE.md, .review/handoff.md, and the complete scoped Git diff
defined by that handoff. This is the only open-ended discovery review. Identify
all material findings in this single pass.

Prioritize bugs, regressions, security issues, contract breaks, manifest wiring
issues, tests missing for changed behavior, deployment/migration risks, and
layering violations. Ignore cosmetic style unless it causes a defect. Do not
expand beyond the declared task or reopen accepted/out-of-scope work.

The sandbox is intentionally read-only. Do not modify any file. Return the full
review document as your final message, following
.review/codex-review.example.md. The orchestrator writes that final message to
.review/codex-review.md. Use CHANGES_REQUIRED only while a BLOCKER or HIGH
finding remains; otherwise use READY_FOR_FINAL_VALIDATION.
"@
} else {
    $prompt = @"
This is review pass 2 of 2 -- CLOSURE_ONLY for: $Task

Read AGENTS.md, CLAUDE.md, .review/handoff.md,
.review/codex-review-pass1.md, and the corrective diff defined by the handoff.
Do not perform a new open-ended review.

Verify only:
1. closure of accepted pass-1 findings;
2. preservation of the original acceptance criteria;
3. regressions directly introduced by the corrective diff.

Do not report pre-existing issues, deferred findings, accepted risks, unrelated
improvements, or cosmetic observations. A new finding is valid only when you
show causal evidence that the corrective diff introduced it.

The sandbox is intentionally read-only. Do not modify any file. Return the full
final review document as your final message, following
.review/codex-review.example.md. The orchestrator writes that message to
.review/codex-review.md. This is the final Codex pass: no third general review is
allowed.
"@
}

New-Item -ItemType Directory -Force $ReviewDir | Out-Null
$arguments = @(
    "exec",
    "--ephemeral",
    "--sandbox", "read-only",
    "--cd", $ProjectRoot,
    "--output-last-message", $ReviewPath
)
if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $arguments += @("--model", $Model)
}
$arguments += "-"

if ($DryRun) {
    Write-Output "Codex executable: $codexExecutable"
    Write-Output "Command: $codexExecutable $($arguments -join ' ')"
    Write-Output ""
    Write-Output $prompt
    exit 0
}

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$loginStatusOutput = @(& $codexExecutable login status 2>&1)
$loginStatusExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousErrorActionPreference
if ($loginStatusExitCode -ne 0) {
    throw @"
Codex CLI was found at:
$codexExecutable

but it is not authenticated in this user environment. The Codex chat/IDE session
and Codex CLI do not necessarily share authentication. Run this one-time command
from your normal terminal, complete the browser/device flow, then relaunch the
delivery loop:

& "$codexExecutable" login --device-auth

CLI response:
$($loginStatusOutput -join [Environment]::NewLine)
"@
}

Write-Host "Starting Codex review pass $ReviewPass/2 ($expectedMode)..." -ForegroundColor Cyan
$prompt | & $codexExecutable @arguments
if ($LASTEXITCODE -ne 0) {
    throw "codex exec failed with exit code $LASTEXITCODE."
}
if (-not (Test-Path $ReviewPath)) {
    throw "codex exec completed without producing .review/codex-review.md."
}

$review = [System.IO.File]::ReadAllText($ReviewPath)
$statusMatch = [regex]::Match(
    $review,
    "(?ms)^## Status\s+(CHANGES_REQUIRED|READY_FOR_FINAL_VALIDATION)\s*$"
)
if (-not $statusMatch.Success) {
    throw "Codex review has no valid ## Status value. Inspect .review/codex-review.md."
}

$status = $statusMatch.Groups[1].Value
if ($ReviewPass -eq 1) {
    Copy-Item -LiteralPath $ReviewPath -Destination $PassOnePath -Force
}

Write-Host "Codex pass $ReviewPass/2 completed: $status" -ForegroundColor Green
Write-Output $status
