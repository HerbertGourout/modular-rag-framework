[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Task,

    [Parameter(Mandatory = $true)]
    [string]$Base,

    [ValidateSet(1, 2)]
    [int]$ReviewPass = 1,

    [string]$CorrectiveBase,

    [ValidateSet("LOW", "NORMAL", "HIGH")]
    [string]$RiskLevel = "NORMAL",

    [string[]]$AcceptanceCriteria = @(),
    [string[]]$DesignDecision = @(),
    [string[]]$ValidationRun = @(),
    [string[]]$ValidationUnavailable = @(),
    [string[]]$KnownLimitation = @(),
    [string[]]$OutOfScope = @(),
    [string[]]$Path = @(),
    [string]$PremiumReason = "",
    [string]$OutputPath = ".review/handoff.md",
    [switch]$PrintOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Git {
    param([string[]]$Arguments)

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = @(& git -C $ProjectRoot @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousErrorActionPreference
    if ($exitCode -ne 0) {
        throw "git $($Arguments -join ' ') failed:`n$($output -join [Environment]::NewLine)"
    }
    # Git may emit non-fatal environment warnings on stderr. Do not put those
    # PowerShell ErrorRecord objects into the generated Markdown inventory.
    return @($output | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] })
}

function Resolve-Commit {
    param([string]$Reference)

    $resolved = @(Invoke-Git -Arguments @("rev-parse", "--verify", "$Reference^{commit}"))
    return ([string]$resolved[0]).Trim()
}

function Add-Bullets {
    param(
        [System.Collections.Generic.List[string]]$Lines,
        [string[]]$Values,
        [string]$EmptyValue = "- None reported."
    )

    if ($Values.Count -eq 0) {
        $Lines.Add($EmptyValue)
        return
    }
    foreach ($value in $Values) {
        $Lines.Add("- $value")
    }
}

if ($ReviewPass -eq 2 -and [string]::IsNullOrWhiteSpace($CorrectiveBase)) {
    throw "-CorrectiveBase is required for review pass 2. Use the pass-1 implementation checkpoint."
}

$baseCommit = Resolve-Commit $Base
$headCommit = Resolve-Commit "HEAD"
$branchOutput = @(Invoke-Git -Arguments @("branch", "--show-current"))
$branch = ([string]$branchOutput[0]).Trim()
$reviewMode = if ($ReviewPass -eq 1) { "DISCOVERY" } else { "CLOSURE_ONLY" }
$correctiveCommit = if ($ReviewPass -eq 2) { Resolve-Commit $CorrectiveBase } else { "N/A" }
$reviewAnchor = if ($ReviewPass -eq 2) { $correctiveCommit } else { $baseCommit }

$pathArguments = @("--") + $Path
$trackedArguments = @("diff", "--name-status", $reviewAnchor) + $pathArguments
$statArguments = @("diff", "--stat", $reviewAnchor) + $pathArguments
$overallStatArguments = @("diff", "--stat", $baseCommit) + $pathArguments
$untrackedArguments = @("ls-files", "--others", "--exclude-standard") + $pathArguments

$trackedChanges = Invoke-Git -Arguments $trackedArguments
$diffSummary = Invoke-Git -Arguments $statArguments
$overallDiffSummary = Invoke-Git -Arguments $overallStatArguments
$untrackedFiles = Invoke-Git -Arguments $untrackedArguments
$workingTreeStatus = Invoke-Git -Arguments @("status", "--short")
$scopeDescription = if ($Path.Count -eq 0) { "complete working tree" } else { $Path -join ", " }
$checkpointDescription = if ($workingTreeStatus.Count -eq 0) {
    $headCommit
} else {
    "$headCommit (working tree changes are not checkpointed)"
}

$generated = [System.Collections.Generic.List[string]]::new()
$generated.Add("<!-- BEGIN GENERATED REVIEW CONTEXT -->")
$generated.Add("## Review identity")
$generated.Add("")
$generated.Add("- Task: $Task")
$generated.Add("- Risk level: ``$RiskLevel``")
$generated.Add("- Review pass: ``$ReviewPass/2``")
$generated.Add("- Review mode: ``$reviewMode``")
$generated.Add("- Base commit: ``$baseCommit``")
$generated.Add("- Implementation checkpoint / current HEAD: $checkpointDescription")
$generated.Add("- Corrective base: ``$correctiveCommit``")
$generated.Add("- Branch: ``$branch``")
$generated.Add("- Review path scope: $scopeDescription")
$generated.Add("- Premium reason: $(if ($PremiumReason) { $PremiumReason } else { 'None.' })")
$generated.Add("")
$generated.Add("## Git change inventory")
$generated.Add("")
$generated.Add("### Review diff (``$reviewAnchor`` to working tree)")
$generated.Add("")
$generated.Add("``````text")
if ($trackedChanges.Count -eq 0) { $generated.Add("No tracked changes.") } else { $generated.AddRange([string[]]$trackedChanges) }
$generated.Add("``````")
$generated.Add("")
$generated.Add("### Untracked files")
$generated.Add("")
$generated.Add("``````text")
if ($untrackedFiles.Count -eq 0) { $generated.Add("No untracked files.") } else { $generated.AddRange([string[]]$untrackedFiles) }
$generated.Add("``````")
$generated.Add("")
$generated.Add("### Review diff summary")
$generated.Add("")
$generated.Add("``````text")
if ($diffSummary.Count -eq 0) { $generated.Add("No tracked diff.") } else { $generated.AddRange([string[]]$diffSummary) }
$generated.Add("``````")
$generated.Add("")
$generated.Add("### Overall task diff summary (``$baseCommit`` to working tree)")
$generated.Add("")
$generated.Add("``````text")
if ($overallDiffSummary.Count -eq 0) { $generated.Add("No tracked diff.") } else { $generated.AddRange([string[]]$overallDiffSummary) }
$generated.Add("``````")
$generated.Add("")
$generated.Add("### Working tree status")
$generated.Add("")
$generated.Add("``````text")
if ($workingTreeStatus.Count -eq 0) { $generated.Add("Clean.") } else { $generated.AddRange([string[]]$workingTreeStatus) }
$generated.Add("``````")
$generated.Add("<!-- END GENERATED REVIEW CONTEXT -->")

$generatedBlock = $generated -join [Environment]::NewLine
$resolvedOutput = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $ProjectRoot $OutputPath
}

if (Test-Path $resolvedOutput) {
    $existing = [System.IO.File]::ReadAllText($resolvedOutput)
    $pattern = "(?s)<!-- BEGIN GENERATED REVIEW CONTEXT -->.*?<!-- END GENERATED REVIEW CONTEXT -->"
    if (-not [regex]::IsMatch($existing, $pattern)) {
        throw "$OutputPath exists but has no generated-context markers; refusing to overwrite semantic content."
    }
    $regex = [regex]::new($pattern)
    $evaluator = [System.Text.RegularExpressions.MatchEvaluator]{ param($match) $generatedBlock }
    $document = $regex.Replace($existing, $evaluator, 1)
} else {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add("# Claude Code to Codex Handoff")
    $lines.Add("")
    $lines.Add($generatedBlock)
    $lines.Add("")
    $lines.Add("## Acceptance criteria")
    $lines.Add("")
    if ($AcceptanceCriteria.Count -eq 0) {
        $lines.Add("- [ ] Complete before requesting review.")
    } else {
        foreach ($criterion in $AcceptanceCriteria) { $lines.Add("- [ ] $criterion") }
    }
    $lines.Add("")
    $lines.Add("## Scope")
    $lines.Add("")
    $lines.Add("### Out of scope")
    $lines.Add("")
    Add-Bullets $lines $OutOfScope
    $lines.Add("")
    $lines.Add("## Design decisions")
    $lines.Add("")
    Add-Bullets $lines $DesignDecision
    $lines.Add("")
    $lines.Add("## Validation executed")
    $lines.Add("")
    Add-Bullets $lines $ValidationRun
    $lines.Add("")
    $lines.Add("## Validation unavailable")
    $lines.Add("")
    Add-Bullets $lines $ValidationUnavailable
    $lines.Add("")
    $lines.Add("## Known limitations and accepted risks")
    $lines.Add("")
    Add-Bullets $lines $KnownLimitation
    $lines.Add("")
    $lines.Add("## Finding resolution (pass 2 only)")
    $lines.Add("")
    $lines.Add("| Finding | Decision | Change made | Test/evidence |")
    $lines.Add("|---|---|---|---|")
    $lines.Add("| | ``FIXED`` / ``DEFERRED`` / ``ACCEPTED_RISK`` / ``REJECTED`` | | |")
    $lines.Add("")
    $lines.Add("## Reviewer instructions")
    $lines.Add("")
    if ($ReviewPass -eq 1) {
        $lines.Add("Perform the only open-ended review of the complete task diff. Report all material findings in one pass.")
    } else {
        $lines.Add("Do not perform a new open-ended review. Verify only accepted finding closure, original acceptance criteria, and regressions directly introduced by the corrective diff.")
    }
    $document = $lines -join [Environment]::NewLine
}

if ($PrintOnly) {
    Write-Output $document
} else {
    $parent = Split-Path -Parent $resolvedOutput
    New-Item -ItemType Directory -Force $parent | Out-Null
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($resolvedOutput, $document + [Environment]::NewLine, $utf8NoBom)
    Write-Host "Prepared $OutputPath for review pass $ReviewPass/2 ($reviewMode)."
    Write-Host "Complete the semantic sections before handing the diff to Codex."
}
