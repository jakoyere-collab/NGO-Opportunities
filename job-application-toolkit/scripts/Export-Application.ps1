<#
.SYNOPSIS
Converts the drafted Markdown documents in an application folder into .docx
files, ready to submit.

.DESCRIPTION
Looks for cv-tailored.md, cover-letter.md, and any other drafted *.md file
in the application folder (e.g. selection-criteria.md), and writes a
matching .docx into an export/ subfolder.

Prefers pandoc, if installed, for full Markdown formatting fidelity (bold,
headings, bullets). Falls back to Microsoft Word automation on Windows when
pandoc isn't found — plain text only, no Markdown formatting carries over.
With neither available, leaves the Markdown as-is and explains how to
convert it by hand.

.PARAMETER ApplicationFolder
Folder name (e.g. "2026-08-30_save-the-children_meal-officer") or a full
path. A bare name is resolved under applications/.

.EXAMPLE
./Export-Application.ps1 -ApplicationFolder 2026-08-30_save-the-children_meal-officer
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $ApplicationFolder
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'JobToolkit.psm1') -Force

$appsRoot = Get-ApplicationsRoot
$folderPath = if (Test-Path $ApplicationFolder) {
    (Resolve-Path $ApplicationFolder).ProviderPath
} else {
    Join-Path $appsRoot $ApplicationFolder
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

$usePandoc = Test-CommandExists 'pandoc'
$isWindowsHost = ($PSVersionTable.PSEdition -eq 'Desktop') -or ($IsWindows -eq $true)

foreach ($md in $mdFiles) {
    $outPath = Join-Path $exportDir ([System.IO.Path]::GetFileNameWithoutExtension($md.Name) + '.docx')

    if ($usePandoc) {
        & pandoc $md.FullName -o $outPath
        Write-Host "Exported $($md.Name) -> $outPath (via pandoc)"
        continue
    }

    if ($isWindowsHost) {
        try {
            $word = New-Object -ComObject Word.Application
            $word.Visible = $false
            $doc = $word.Documents.Add()
            $doc.Content.Text = Get-Content -Raw $md.FullName
            $doc.SaveAs([ref] $outPath, [ref] 16)  # 16 = wdFormatXMLDocument (.docx)
            $doc.Close()
            $word.Quit()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
            Write-Host "Exported $($md.Name) -> $outPath (via Word — plain text only, no Markdown formatting; install pandoc for proper formatting: https://pandoc.org/installing.html)" -ForegroundColor Yellow
            continue
        } catch {
            Write-Warning "Word automation unavailable or failed for $($md.Name): $_"
        }
    }

    Write-Host "Couldn't convert $($md.Name) automatically (no pandoc, no Word found). Open it and paste into Word/Google Docs, or install pandoc: https://pandoc.org/installing.html" -ForegroundColor Yellow
}
