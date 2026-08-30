# Job Application Toolkit

A personal workflow for tailoring a CV, cover letter, and any other
requirement a job description asks for — one application at a time, kept
honest to your real CV.

PowerShell handles the mechanical parts (folder setup, pulling text out of
your JD/CV files, tracking status, exporting to `.docx`). The actual
writing — reading the job description, comparing it against your CV, and
drafting genuinely tailored, human-sounding text — is done by Claude,
following the rules in
[`.claude/skills/tailor-application/SKILL.md`](../.claude/skills/tailor-application/SKILL.md).
Those rules are the point of this toolkit: **never invent experience** —
where the job description calls for something your CV doesn't show, you
get asked about it, not papered over.

## Privacy — read this first

`applications/` (created the first time you run a script) holds your real
CV, real job descriptions, and drafted application text. It's listed in
`.gitignore` so it's never committed to this repo, which is public. Keep it
that way — don't move your personal files elsewhere in the repo, and check
`git status` before committing if you're ever unsure what's staged.

## Prerequisites

- PowerShell 7+ (cross-platform) or Windows PowerShell 5.1.
- Optional, for `.pdf` job descriptions or CVs: `pdftotext` (from
  poppler-utils) on PATH, so text can be auto-extracted. Without it, paste
  the text in by hand when prompted.
- Optional, for proper `.docx` formatting on export: [pandoc](https://pandoc.org/installing.html).
  Without it, export falls back to Microsoft Word automation on Windows
  (plain text only), or leaves the draft as Markdown for you to paste in
  yourself.
- Claude Code (or another Claude interface) open in this repo, for the
  actual drafting step.

## Workflow

1. **Start a new application:**
   ```powershell
   cd job-application-toolkit/scripts
   ./New-Application.ps1 -JobDescriptionPath ~/Downloads/jd.pdf -CvPath ~/Documents/CV.docx -Company "Save the Children" -Role "MEAL Officer"
   ```
   The first run needs `-CvPath`; after that it's optional — the toolkit
   reuses the CV you gave it as a saved master CV. This creates
   `applications/2026-08-30_save-the-children_meal-officer/` with the JD,
   your CV, best-effort extracted plain text for both, and empty
   `gap-questions.md` / `notes.md` files.

2. **Ask Claude to tailor it.** In Claude Code, from this repo, say
   something like *"tailor the application in
   applications/2026-08-30_save-the-children_meal-officer"*. Claude reads
   the skill automatically, compares the JD against your CV, and either
   drafts straight away or asks you specific questions first if the JD
   needs something your CV doesn't show evidence of.

3. **Answer any open questions** — either inline in that application's
   `gap-questions.md`, or directly in the chat. Nothing gets written into
   your CV or cover letter as fact until it's backed by your real CV or by
   your answer.

4. **Review the drafts**: `cv-tailored.md`, `cover-letter.md`, and any
   other file the JD required (e.g. `selection-criteria.md`) land in the
   same application folder. Read them, edit them, make them sound like
   you — these are a strong first draft, not a submit-unread final.

5. **Export to `.docx`:**
   ```powershell
   ./Export-Application.ps1 -ApplicationFolder 2026-08-30_save-the-children_meal-officer
   ```
   Writes `.docx` copies into that application's `export/` folder.

6. **Check status across everything:**
   ```powershell
   ./Show-Applications.ps1
   ```

## Structure

```
job-application-toolkit/
├── README.md                  — this file
├── scripts/
│   ├── JobToolkit.psm1        — shared helpers (text extraction, slugs, paths)
│   ├── New-Application.ps1    — start a new application
│   ├── Export-Application.ps1 — Markdown drafts -> .docx
│   └── Show-Applications.ps1  — status across all applications
├── templates/
│   ├── cv-master-template.md
│   ├── cover-letter-template.md
│   ├── gap-questions-template.md
│   └── notes-template.md
└── applications/               — gitignored; created on first run
    ├── _master-cv.*            — your saved CV, reused across applications
    ├── tracker.csv             — simple log of every application started
    └── <date>_<org>_<role>/    — one folder per application
```
