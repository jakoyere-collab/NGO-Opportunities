<#
.SYNOPSIS
Shared helper functions used by the Job Application Toolkit scripts.

.DESCRIPTION
Not run directly - imported by New-Application.ps1, Export-Application.ps1,
and Show-Applications.ps1. Keeping these here once instead of copy-pasted
into each script.
#>

function Get-ToolkitRoot {
    # $PSScriptRoot here is this module's own folder (scripts/), regardless
    # of which script imported it or what the caller's working directory is.
    # This is the *code* location (templates live here) - never personal data.
    Split-Path -Parent $PSScriptRoot
}

function Get-DataRoot {
    <#
    .SYNOPSIS
    Resolves (and creates, on first call) the local folder that holds your
    real CVs, job descriptions, and drafted application text.

    .DESCRIPTION
    Deliberately outside the git repo - this is personal data, and the repo
    is public. Defaults to <your Desktop>\JobApplications, resolved via
    .NET's SpecialFolder API (so it lands in the right place even when
    Desktop is OneDrive-redirected, common on managed Windows machines).
    Override by setting $env:JOB_APP_TOOLKIT_HOME before running a script,
    e.g. in your PowerShell profile: $env:JOB_APP_TOOLKIT_HOME = 'D:\JobApps'
    #>
    $root = if ($env:JOB_APP_TOOLKIT_HOME) {
        $env:JOB_APP_TOOLKIT_HOME
    } else {
        $desktop = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
        Join-Path $desktop 'JobApplications'
    }
    foreach ($sub in 'Inbox', 'Applications', 'Output') {
        $subPath = Join-Path $root $sub
        if (-not (Test-Path $subPath)) {
            New-Item -ItemType Directory -Path $subPath -Force | Out-Null
        }
    }
    $root
}

function Get-InboxRoot { Join-Path (Get-DataRoot) 'Inbox' }
function Get-ApplicationsFolderRoot { Join-Path (Get-DataRoot) 'Applications' }
function Get-OutputRoot { Join-Path (Get-DataRoot) 'Output' }

function New-SlugName {
    param(
        # AllowEmptyString matters here: a bare [Parameter(Mandatory)] string
        # parameter rejects "" at the binding layer, before the function body
        # (and its own empty -> 'untitled' fallback below) ever runs.
        [Parameter(Mandatory)] [AllowEmptyString()] [string] $Text,
        [int] $MaxLength = 40
    )
    $slug = $Text.ToLowerInvariant()
    $slug = [regex]::Replace($slug, '[^a-z0-9]+', '-').Trim('-')
    if ($slug.Length -gt $MaxLength) {
        $slug = $slug.Substring(0, $MaxLength).TrimEnd('-')
    }
    if ([string]::IsNullOrWhiteSpace($slug)) { $slug = 'untitled' }
    $slug
}

function Test-CommandExists {
    param([Parameter(Mandatory)] [string] $Name)
    [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function ConvertFrom-DocxToText {
    <#
    .SYNOPSIS
    Best-effort plain-text extraction from a .docx by reading its
    word/document.xml directly - a .docx is just a zip archive, so this
    needs no external dependency (pandoc, Word, etc.), only .NET's
    built-in ZipFile class.
    #>
    param([Parameter(Mandatory)] [string] $Path)

    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
    $resolved = (Resolve-Path $Path).ProviderPath
    $zip = [System.IO.Compression.ZipFile]::OpenRead($resolved)
    try {
        $entry = $zip.GetEntry('word/document.xml')
        if (-not $entry) { return $null }
        $stream = $entry.Open()
        try {
            $reader = New-Object System.IO.StreamReader($stream)
            $xml = $reader.ReadToEnd()
        } finally {
            $stream.Dispose()
        }
    } finally {
        $zip.Dispose()
    }

    # Turn paragraph/line-break boundaries into newlines before stripping
    # tags, so the extracted text keeps the document's paragraph structure
    # instead of collapsing into one run-on line.
    $xml = $xml -replace '</w:p>', "`n"
    $xml = $xml -replace '<w:br[^/]*/>', "`n"
    $text = [regex]::Replace($xml, '<[^>]+>', '')
    $text = [System.Net.WebUtility]::HtmlDecode($text)
    ($text -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' }) -join "`n"
}

function ConvertFrom-PdfToText {
    <#
    .SYNOPSIS
    Extracts text from a PDF via pdftotext (poppler-utils) if it's on PATH.
    There's no dependency-free way to parse PDF text in plain PowerShell, so
    this degrades honestly - it warns and returns nothing rather than
    guessing - when pdftotext isn't installed, or when the PDF is a scanned
    image with no text layer at all.
    #>
    param([Parameter(Mandatory)] [string] $Path)

    if (-not (Test-CommandExists 'pdftotext')) {
        Write-Warning "pdftotext not found (install poppler-utils to auto-extract PDF text: e.g. 'winget install poppler' / 'brew install poppler' / 'apt install poppler-utils'). Skipping extraction for $Path - paste the text in manually, or convert it to .docx/.txt first."
        return $null
    }
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        & pdftotext -layout $Path $tmp 2>$null
        $text = Get-Content -Raw -ErrorAction SilentlyContinue $tmp
        if ([string]::IsNullOrWhiteSpace($text)) {
            Write-Warning "pdftotext returned no text for $Path - it may be a scanned image with no text layer. Paste the text in manually."
            return $null
        }
        $text
    } finally {
        Remove-Item $tmp -ErrorAction SilentlyContinue
    }
}

function Get-PlainTextFromFile {
    <#
    .SYNOPSIS
    Best-effort plain-text extraction dispatched by file extension.
    Returns $null (with a warning already printed) when extraction isn't
    possible - callers should treat that as "ask the user to paste it in",
    never as empty-but-fine.
    #>
    param([Parameter(Mandatory)] [string] $Path)

    if (-not (Test-Path $Path)) {
        Write-Warning "File not found: $Path"
        return $null
    }
    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    switch ($ext) {
        { $_ -in '.txt', '.md' } { Get-Content -Raw $Path }
        '.docx' { ConvertFrom-DocxToText -Path $Path }
        '.pdf' { ConvertFrom-PdfToText -Path $Path }
        default {
            Write-Warning "Don't know how to extract text from '$ext' files: $Path"
            $null
        }
    }
}

Export-ModuleMember -Function `
    Get-ToolkitRoot, Get-DataRoot, Get-InboxRoot, Get-ApplicationsFolderRoot, Get-OutputRoot, `
    New-SlugName, Test-CommandExists, `
    Get-PlainTextFromFile, ConvertFrom-DocxToText, ConvertFrom-PdfToText
