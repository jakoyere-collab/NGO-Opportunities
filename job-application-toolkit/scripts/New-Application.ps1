<#
.SYNOPSIS
Starts a new tailored job application: creates a working folder, copies in
the job description and CV, and extracts plain text from each where possible.

.DESCRIPTION
Run this first for every new application. It only does the mechanical
part — folder setup, copying files, best-effort text extraction. It never
writes the tailored CV or cover letter itself; that's done by Claude,
following the rules in .claude/skills/tailor-application/SKILL.md, using the
files this script lays down. See ../README.md for the full workflow.

.PARAMETER JobDescriptionPath
Path to the job description file (.txt, .md, .docx, or .pdf).

.PARAMETER CvPath
Path to your CV (.txt, .md, .docx, or .pdf). Optional after the first run —
if omitted, the toolkit reuses the master CV saved from a previous run.

.PARAMETER Company
Organization name, used to name the application folder. Prompted for if
omitted.

.PARAMETER Role
Role title, used to name the application folder. Prompted for if omitted.

.EXAMPLE
./New-Application.ps1 -JobDescriptionPath ~/Downloads/jd.pdf -CvPath ~/Documents/CV.docx -Company "Save the Children" -Role "MEAL Officer"

.EXAMPLE
./New-Application.ps1 -JobDescriptionPath ~/Downloads/jd2.pdf -Company "Mercy Corps" -Role "Program Officer"
# Reuses the master CV saved by the first run above.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $JobDescriptionPath,
    [string] $CvPath,
    [string] $Company,
    [string] $Role
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'JobToolkit.psm1') -Force

if (-not (Test-Path $JobDescriptionPath)) {
    throw "Job description not found: $JobDescriptionPath"
}

$appsRoot = Get-ApplicationsRoot
$masterCv = Get-ChildItem $appsRoot -Filter '_master-cv.*' -File -ErrorAction SilentlyContinue | Select-Object -First 1

if (-not $CvPath -and -not $masterCv) {
    throw "No -CvPath given and no saved master CV found yet. Pass -CvPath the first time you run this."
}
if (-not $CvPath) {
    $CvPath = $masterCv.FullName
    Write-Host "Using saved master CV: $CvPath"
}
if (-not (Test-Path $CvPath)) {
    throw "CV not found: $CvPath"
}

if (-not $Company) { $Company = Read-Host 'Organization name' }
if (-not $Role) { $Role = Read-Host 'Role title' }

$date = Get-Date -Format 'yyyy-MM-dd'
$baseName = "$($date)_$(New-SlugName $Company)_$(New-SlugName $Role)"
$folderName = $baseName
$suffix = 1
while (Test-Path (Join-Path $appsRoot $folderName)) {
    $suffix++
    $folderName = "$baseName-$suffix"
}
$appFolder = Join-Path $appsRoot $folderName
New-Item -ItemType Directory -Path $appFolder | Out-Null

$jdExt = [System.IO.Path]::GetExtension($JobDescriptionPath)
$cvExt = [System.IO.Path]::GetExtension($CvPath)
Copy-Item $JobDescriptionPath (Join-Path $appFolder "job-description$jdExt")
Copy-Item $CvPath (Join-Path $appFolder "cv-source$cvExt")

if (-not $masterCv) {
    Copy-Item $CvPath (Join-Path $appsRoot "_master-cv$cvExt")
    Write-Host "Saved this CV as your reusable master CV (applications/_master-cv$cvExt) — future runs can omit -CvPath."
}

$jdText = Get-PlainTextFromFile (Join-Path $appFolder "job-description$jdExt")
if ($jdText) {
    Set-Content -Path (Join-Path $appFolder 'job-description.extracted.txt') -Value $jdText -Encoding utf8
}

$cvText = Get-PlainTextFromFile (Join-Path $appFolder "cv-source$cvExt")
if ($cvText) {
    Set-Content -Path (Join-Path $appFolder 'cv-source.extracted.txt') -Value $cvText -Encoding utf8
}

$templatesDir = Join-Path (Get-ToolkitRoot) 'templates'
Copy-Item (Join-Path $templatesDir 'gap-questions-template.md') (Join-Path $appFolder 'gap-questions.md')
Copy-Item (Join-Path $templatesDir 'notes-template.md') (Join-Path $appFolder 'notes.md')

[pscustomobject]@{
    Date    = $date
    Folder  = $folderName
    Company = $Company
    Role    = $Role
} | Export-Csv -Path (Join-Path $appsRoot 'tracker.csv') -Append -NoTypeInformation -Encoding utf8

Write-Host ''
Write-Host "Created $appFolder" -ForegroundColor Green
Write-Host "Next: open this repo in Claude Code and ask it to tailor the application in applications/$folderName"
Write-Host '      (it will follow .claude/skills/tailor-application/SKILL.md, and will ask you before assuming any skill your CV doesn''t already show).'
if (-not $jdText) {
    Write-Host "Note: couldn't auto-extract the job description text — paste it into job-description.extracted.txt yourself before asking Claude to draft anything." -ForegroundColor Yellow
}
if (-not $cvText) {
    Write-Host "Note: couldn't auto-extract the CV text — paste it into cv-source.extracted.txt yourself before asking Claude to draft anything." -ForegroundColor Yellow
}
