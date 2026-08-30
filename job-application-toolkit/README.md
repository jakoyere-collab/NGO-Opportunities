# Job Application Toolkit

A personal workflow for tailoring a CV, cover letter, and any other
requirement a job description asks for — one application at a time, kept
honest to your real CV, kept off the public repo.

PowerShell handles the mechanical parts (picking up files you drop in,
pulling text out of your JD/CV, tracking status, exporting to `.docx`). The
actual writing — reading the job description, comparing it against your
CV, and drafting genuinely tailored, human-sounding text — is done by
Claude, following the rules in
[`.claude/skills/tailor-application/SKILL.md`](../.claude/skills/tailor-application/SKILL.md).
Those rules are the point of this toolkit: **never invent experience** —
where the job description calls for something your CV doesn't show, you
get asked about it, not papered over.

## Running this for real: it has to be on your own machine

This code lives in a public GitHub repo, but nothing in this workflow —
your CV, job descriptions, or drafts — should ever be *processed* anywhere
but your own computer. If you're reading this from a Claude Code session
running in the cloud (web/mobile "Claude Code on the web"), that session's
filesystem is a temporary container, not your Desktop — running the
scripts there would not touch your real files, and its storage is deleted
when the session ends. To actually use this toolkit:

1. Install [Claude Code](https://claude.com/claude-code) locally (or use it
   through an IDE extension / desktop app), and have PowerShell available
   — Windows already has it; PowerShell 7+ is the cross-platform version if
   you're elsewhere.
2. Get this repo onto your machine: `git clone` it (keeps you able to pull
   future updates to the toolkit), or just copy the `job-application-toolkit/`
   and `.claude/skills/tailor-application/` folders into a project folder
   of your own if you'd rather not have the whole public site locally too.
3. Open a terminal **in that folder** and run `claude` there — that's what
   makes Claude Code auto-discover the skill. PowerShell scripts are run
   from a separate PowerShell terminal, also in that folder (`cd
   job-application-toolkit/scripts`).

From there, everything below happens locally: your files, the PowerShell
scripts, and Claude Code all running on your own machine. The one thing
that still leaves your machine is the job description/CV *text* itself,
sent to Claude as part of the conversation when you ask it to draft —
that's unavoidable for AI-quality writing, no matter which tool does it.

## Data protection

- **Personal data lives outside the repo entirely.** The first time any
  script runs, it creates `Desktop\JobApplications\` (Inbox, Applications,
  Output) — not inside the cloned repo, so there's no `.gitignore` rule
  standing between your CV and a public commit; it's simply never in a git
  working tree. Override the location with `$env:JOB_APP_TOOLKIT_HOME` if
  you'd rather it lived somewhere else (e.g. a specific drive or an
  encrypted folder) — set that before running a script, or add it to your
  PowerShell profile to make it permanent.
- **Only the code and templates are in the repo** — no filenames, paths, or
  content from your applications are ever written into a tracked file.
- **Don't paste your CV or a job description into third-party web tools**
  (online "humanizers," random converters, etc.) — keep it to Claude and
  your own machine.
- If `Desktop` syncs to a cloud drive you control (OneDrive, iCloud), that's
  fine — it's still only reachable by you. A shared or public machine is
  not an appropriate place to run this.

## Prerequisites

- PowerShell 7+ (cross-platform) or Windows PowerShell 5.1.
- Optional, for `.pdf` job descriptions or CVs: `pdftotext` (from
  poppler-utils) on PATH, so text can be auto-extracted. Without it, paste
  the text in by hand when prompted.
- Optional, for proper `.docx` formatting on export: [pandoc](https://pandoc.org/installing.html).
  Without it, export falls back to Microsoft Word automation on Windows
  (plain text only), or leaves the draft as Markdown for you to paste in
  yourself.
- Claude Code, run from this project folder, for the actual drafting step.

## Workflow

1. **Drop files into Inbox.** Find `Desktop\JobApplications\Inbox\` (created
   automatically the first time you run any script) and drop in **both**
   the job description and your CV, every time — nothing is remembered
   between applications, so this is required on every run, not just the
   first. Your CV's filename needs "cv" or "resume" in it (e.g. `CV.docx`,
   `JaneDoe_Resume.pdf`) so the script can tell it apart from the job
   description automatically. Any other file in Inbox is treated as the JD,
   so keep only one job description in there at a time.

2. **Run the intake script:**
   ```powershell
   cd job-application-toolkit/scripts
   ./New-Application.ps1
   ```
   It'll ask for the organization name and role title, then create
   `Applications\2026-08-30_save-the-children_meal-officer\` with the JD,
   your CV, best-effort extracted plain text for both, and empty
   `gap-questions.md` / `notes.md` files — and clears Inbox back out.
   (You can skip Inbox entirely and pass explicit paths instead:
   `./New-Application.ps1 -JobDescriptionPath ~/Downloads/jd.pdf -CvPath ~/Documents/CV.docx -Company "Save the Children" -Role "MEAL Officer"`.)

3. **Ask Claude to tailor it.** In Claude Code, from this project folder,
   say something like *"tailor the application in
   Applications/2026-08-30_save-the-children_meal-officer"*. Claude reads
   the skill automatically, compares the JD against your CV, and either
   drafts straight away or asks you specific questions first if the JD
   needs something your CV doesn't show evidence of.

4. **Answer any open questions** — either inline in that application's
   `gap-questions.md`, or directly in the chat. Nothing gets written into
   your CV or cover letter as fact until it's backed by your real CV or by
   your answer.

5. **Review the drafts**: `cv-tailored.md`, `cover-letter.md`, and any
   other file the JD required (e.g. `selection-criteria.md`) land in the
   same application folder. Read them, edit them, make them sound like
   you — these are a strong first draft, not a submit-unread final.

6. **Export to `.docx`:**
   ```powershell
   ./Export-Application.ps1 -ApplicationFolder 2026-08-30_save-the-children_meal-officer
   ```
   Writes `.docx` copies into that application's own `export\` folder, and
   also into **`Desktop\JobApplications\Output\`** — one flat folder,
   clearly named (e.g. `2026-08-30 Save the Children - MEAL Officer -
   CV.docx`), which is the place to go review and download from.

7. **Check status across everything:**
   ```powershell
   ./Show-Applications.ps1
   ```

## Structure

```
job-application-toolkit/              (in the git repo — code only)
├── README.md                         — this file
├── scripts/
│   ├── JobToolkit.psm1                — shared helpers (data root, text extraction, slugs)
│   ├── New-Application.ps1            — pick up Inbox files, start a new application
│   ├── Export-Application.ps1         — Markdown drafts -> .docx -> Output
│   └── Show-Applications.ps1          — status across all applications
└── templates/
    ├── cv-master-template.md
    ├── cover-letter-template.md
    ├── gap-questions-template.md
    └── notes-template.md

Desktop\JobApplications\              (on your machine only — never in git)
├── Inbox\                             — drop the JD + your CV here, every time
├── Applications\
│   └── <date>_<org>_<role>\           — one folder per application
├── Output\                            — finished .docx files, ready to review/submit
└── tracker.csv                        — simple log of every application started
```
