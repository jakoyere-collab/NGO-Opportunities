<#
.SYNOPSIS
Lists every application folder with a live status.

.DESCRIPTION
Status is computed from what files actually exist in each folder — not from
a hand-maintained field that can drift out of date as you go.

.EXAMPLE
./Show-Applications.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'JobToolkit.psm1') -Force

$appsRoot = Get-ApplicationsRoot
$folders = Get-ChildItem $appsRoot -Directory -ErrorAction SilentlyContinue

if (-not $folders) {
    Write-Host 'No applications yet. Run New-Application.ps1 to start one.'
    return
}

$rows = foreach ($folder in $folders) {
    $hasJd = (Get-ChildItem $folder.FullName -Filter 'job-description.*' -File -ErrorAction SilentlyContinue).Count -gt 0
    $hasCv = (Get-ChildItem $folder.FullName -Filter 'cv-source.*' -File -ErrorAction SilentlyContinue).Count -gt 0

    $openGaps = 0
    $gapFile = Join-Path $folder.FullName 'gap-questions.md'
    if (Test-Path $gapFile) {
        # Named $gapMatches, not $matches — the latter is PowerShell's automatic
        # variable for -match results and shadowing it here would be a footgun.
        $gapMatches = Select-String -Path $gapFile -Pattern '^\s*-\s*\[\s\]' -ErrorAction SilentlyContinue
        $openGaps = @($gapMatches).Count
    }

    $hasCvDraft = Test-Path (Join-Path $folder.FullName 'cv-tailored.md')
    $hasCoverLetter = Test-Path (Join-Path $folder.FullName 'cover-letter.md')

    $exportDir = Join-Path $folder.FullName 'export'
    $hasExport = (Test-Path $exportDir) -and (Get-ChildItem $exportDir -File -ErrorAction SilentlyContinue).Count -gt 0

    $status =
        if (-not $hasJd -or -not $hasCv) { 'Incomplete intake' }
        elseif ($openGaps -gt 0) { "Awaiting your input ($openGaps open question$(if ($openGaps -ne 1) { 's' }))" }
        elseif (-not $hasCvDraft -or -not $hasCoverLetter) { 'Ready to draft' }
        elseif (-not $hasExport) { 'Drafted — not yet exported' }
        else { 'Exported' }

    [pscustomobject]@{
        Application = $folder.Name
        Status      = $status
    }
}

$rows | Sort-Object Application -Descending | Format-Table -AutoSize
