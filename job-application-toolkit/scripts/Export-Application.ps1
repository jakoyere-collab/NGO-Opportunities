<#
.SYNOPSIS
Converts the drafted Markdown documents in an application folder into
.docx files, and copies them into a single Output folder to review and
download from.

.DESCRIPTION
Looks for cv-tailored.md, cover-letter.md, and any other drafted *.md file
in the application folder (e.g. selection-criteria.md). For each, writes a
matching .docx into that application's own export/ subfolder, then copies
it into <data root>\Output with a descriptive name - that's the one folder
to check after running this.

Prefers pandoc, if installed, for full Markdown formatting fidelity (bold,
headings, bullets). Falls back to Microsoft Word automation on Windows when
pandoc isn't found - plain text only, no Markdown formatting carries over.
With neither available, leaves the Markdown as-is and explains how to
convert it by hand.

.PARAMETER ApplicationFolder
Folder name (e.g. "2026-08-30_save-the-children_meal-officer") or a full
path. A bare name is resolved under <data root>\Applications.

.EXAMPLE
./Export-Application.ps1 -ApplicationFolder 2026-08-30_save-the-children_meal-officer
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ApplicationFolder
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'JobToolkit.psm1') -Force

$appsDir = Get-ApplicationsFolderRoot
$folderPath = if (Test-Path $ApplicationFolder) {
    (Resolve-Path $ApplicationFolder).ProviderPath
} else {
    Join-Path $appsDir $ApplicationFolder
}
if (-not (Test-Path $folderPath)) {
    throw "Application folder not found: $ApplicationFolder"
}

$mdFiles = Get-ChildItem $folderPath -Filter '*.md' -File | Where-Object { $_.Name -notin @('gap-questions.md', 'notes.md') }
if (-not $mdFiles) {
    Write-Host "No drafted documents (e.g. cv-tailored.md, cover-letter.md) found yet in $folderPath."
    return
}

$exportDir = Join-Path $folderPath 'export'
New-Item -ItemType Directory -Path $exportDir -Force | Out-Null

$trackerPath = Join-Path (Get-DataRoot) 'tracker.csv'
$trackerRow = $null
if (Test-Path $trackerPath) {
    $folderLeaf = Split-Path $folderPath -Leaf
    $trackerRow = Import-Csv $trackerPath | Where-Object { $_.Folder -eq $folderLeaf } | Select-Object -Last 1
}

function Get-DocLabel([string] $Stem) {
    switch ($Stem) {
        'cv-tailored' { 'CV' }
        'cover-letter' { 'Cover Letter' }
        default { (Get-Culture).TextInfo.ToTitleCase(($Stem -replace '-', ' ')) }
    }
}

$usePandoc = Test-CommandExists 'pandoc'
$isWindowsHost = ($PSVersionTable.PSEdition -eq 'Desktop') -or ($IsWindows -eq $true)

foreach ($md in $mdFiles) {
    $stem = [System.IO.Path]::GetFileNameWithoutExtension($md.Name)
    $outPath = Join-Path $exportDir "$($stem).docx"

    if ($usePandoc) {
        & pandoc $md.FullName -o $outPath
        Write-Host "Exported $($md.Name) -> $outPath (via pandoc)"
    } elseif ($isWindowsHost) {
        try {
            $word = New-Object -ComObject Word.Application
            $word.Visible = $false
            $word.DisplayAlerts = 0  # wdAlertsNone -- an invisible Word instance must never be able to block on a dialog it can't show
            $doc = $word.Documents.Add()
            $doc.Content.Text = Get-Content -Raw $md.FullName
            # Deliberately just the filename, no FileFormat argument: Word
            # infers .docx from the extension, and PowerShell's late-bound
            # COM dispatch has been unreliable here with an explicit
            # [ref]-wrapped FileFormat value (throws "Exception setting
            # SaveAs: Cannot convert ... psobject to Object" in practice).
            $doc.SaveAs([string]$outPath)
            $doc.Close()
            $word.Quit()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
            Write-Host "Exported $($md.Name) -> $outPath (via Word - plain text only, no Markdown formatting; install pandoc for proper formatting: https://pandoc.org/installing.html)" -ForegroundColor Yellow
        } catch {
            Write-Warning "Word automation unavailable or failed for $($md.Name): $_. This path is fragile across Word/PowerShell versions -- installing pandoc (winget install --id JohnMacFarlane.Pandoc) sidesteps it entirely and is the more reliable option."
        }
    } else {
        Write-Host "Couldn't convert $($md.Name) automatically (no pandoc, no Word found). Open it and paste into Word/Google Docs, or install pandoc: https://pandoc.org/installing.html" -ForegroundColor Yellow
    }

    if (Test-Path $outPath) {
        $label = Get-DocLabel $stem
        $outputName = if ($trackerRow) {
            "$($trackerRow.Date) $($trackerRow.Company) - $($trackerRow.Role) - $($label).docx"
        } else {
            "$(Split-Path $folderPath -Leaf) - $($label).docx"
        }
        # Strip characters Windows won't allow in a filename (a free-text
        # Company/Role could contain any of these).
        $outputName = [regex]::Replace($outputName, '[\\/:*?"<>|]', '-')
        Copy-Item $outPath (Join-Path (Get-OutputRoot) $outputName) -Force
        Write-Host "  -> also copied to Output\$outputName" -ForegroundColor Green
    }
}
