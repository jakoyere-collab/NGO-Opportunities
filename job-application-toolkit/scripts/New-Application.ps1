<#
.SYNOPSIS
Starts a new tailored job application from whatever's in your Inbox folder,
or from explicit file paths.

.DESCRIPTION
Default flow: drop the job description (and, first time only, your CV) into
<data root>\Inbox, then run this with no arguments. It picks the files up,
creates a new application folder under <data root>\Applications, copies
them in, extracts plain text where possible, saves/updates your reusable
master CV, and clears Inbox back out.

<data root> defaults to Desktop\JobApplications and is created
automatically outside this git repo — see JobToolkit.psm1's Get-DataRoot
and ../README.md. This script never writes the tailored CV or cover letter
itself; that's done by Claude, following the rules in
.claude/skills/tailor-application/SKILL.md.

Your CV file needs "cv" or "resume" somewhere in its filename so it can be
told apart from the job description automatically — anything else dropped
in Inbox is treated as the job description.

.PARAMETER JobDescriptionPath
Optional. Path to the job description file. Overrides scanning the Inbox.

.PARAMETER CvPath
Optional. Path to your CV. Overrides scanning the Inbox / the saved master CV.

.PARAMETER Company
Organization name, used to name the application folder. Prompted for if
omitted.

.PARAMETER Role
Role title, used to name the application folder. Prompted for if omitted.

.EXAMPLE
./New-Application.ps1
# Picks up whatever's sitting in Inbox.

.EXAMPLE
./New-Application.ps1 -JobDescriptionPath ~/Downloads/jd.pdf -CvPath ~/Documents/CV.docx -Company "Save the Children" -Role "MEAL Officer"
#>
[CmdletBinding()]
param(
    [string] $JobDescriptionPath,
    [string] $CvPath,
    [string] $Company,
    [string] $Role
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'JobToolkit.psm1') -Force

$dataRoot = Get-DataRoot
$inboxDir = Get-InboxRoot
$appsDir = Get-ApplicationsFolderRoot

# Files to clear from Inbox once the application folder is safely set up —
# only populated with files this run actually pulled *from* Inbox, never
# from explicit -JobDescriptionPath/-CvPath arguments.
$inboxMoves = @()

if (-not $JobDescriptionPath -or -not $CvPath) {
    $inboxFiles = Get-ChildItem $inboxDir -File -ErrorAction SilentlyContinue
    $inboxCv = $inboxFiles | Where-Object { $_.BaseName -match '(?i)cv|resume' } | Select-Object -First 1
    $inboxJds = $inboxFiles | Where-Object { $_.FullName -ne $inboxCv.FullName }

    if (-not $JobDescriptionPath) {
        if ($inboxJds.Count -eq 0) {
            throw "No job description found in Inbox ($inboxDir). Drop the JD file in there (and your CV too, first time) and run this again — or pass -JobDescriptionPath."
        }
        if ($inboxJds.Count -gt 1) {
            throw "More than one file in Inbox that doesn't look like your CV — process one job description at a time. Files seen: $($inboxJds.Name -join ', '). If one of these is actually your CV, rename it to include 'cv' or 'resume', or pass -CvPath explicitly."
        }
        $JobDescriptionPath = $inboxJds[0].FullName
        $inboxMoves += $inboxJds[0].FullName
    }
    if (-not $CvPath -and $inboxCv) {
        $CvPath = $inboxCv.FullName
        $inboxMoves += $inboxCv.FullName
    }
}

if (-not (Test-Path $JobDescriptionPath)) {
    throw "Job description not found: $JobDescriptionPath"
}

$masterCv = Get-ChildItem $dataRoot -Filter '_master-cv.*' -File -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $CvPath -and -not $masterCv) {
    throw "No CV found in Inbox and no saved master CV yet. Drop your CV into Inbox ($inboxDir) alongside the job description, or pass -CvPath."
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
while (Test-Path (Join-Path $appsDir $folderName)) {
    $suffix++
    $folderName = "$baseName-$suffix"
}
$appFolder = Join-Path $appsDir $folderName
New-Item -ItemType Directory -Path $appFolder | Out-Null

$jdExt = [System.IO.Path]::GetExtension($JobDescriptionPath)
$cvExt = [System.IO.Path]::GetExtension($CvPath)
Copy-Item $JobDescriptionPath (Join-Path $appFolder "job-description$jdExt")
Copy-Item $CvPath (Join-Path $appFolder "cv-source$cvExt")

# A CV pulled from Inbox is a deliberate "use/update this from now on" signal;
# an explicit -CvPath one-off isn't — it doesn't silently become the default.
if (-not $masterCv -or $inboxMoves -contains $CvPath) {
    Copy-Item $CvPath (Join-Path $dataRoot "_master-cv$cvExt") -Force
    Write-Host "Saved/updated your master CV (JobApplications\_master-cv$cvExt) — future runs reuse it automatically."
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
} | Export-Csv -Path (Join-Path $dataRoot 'tracker.csv') -Append -NoTypeInformation -Encoding utf8

foreach ($path in $inboxMoves) {
    Remove-Item $path -Force -ErrorAction SilentlyContinue
}

Write-Host ''
Write-Host "Created $appFolder" -ForegroundColor Green
Write-Host "Next: open Claude Code in this project folder and ask it to tailor the application in Applications\$folderName"
Write-Host '      (it will follow .claude/skills/tailor-application/SKILL.md, and will ask you before assuming any skill your CV doesn''t already show).'
if (-not $jdText) {
    Write-Host "Note: couldn't auto-extract the job description text — paste it into job-description.extracted.txt yourself before asking Claude to draft anything." -ForegroundColor Yellow
}
if (-not $cvText) {
    Write-Host "Note: couldn't auto-extract the CV text — paste it into cv-source.extracted.txt yourself before asking Claude to draft anything." -ForegroundColor Yellow
}
