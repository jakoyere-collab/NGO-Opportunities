---
name: tailor-application
description: Tailor a CV, cover letter, and any other JD-required materials for one job application, grounded strictly in the candidate's real CV. Asks the user for more context instead of inventing experience when the job description calls for something the CV doesn't show. Use when the user asks to tailor, draft, or write an application for a specific job, points at an applications/<folder> made by New-Application.ps1, or hands over a job description plus a CV.
---

# Tailor a job application

You are drafting application materials for one specific job, for one real
person, based only on their real CV. This is a drafting aid, not a
generator of plausible-sounding fiction — the person applying still has to
be able to defend everything in an interview.

## Inputs

Usually a folder created by `New-Application.ps1`, named
`<name>/` under the toolkit's data root — by default
`Desktop\JobApplications\Applications\<name>\` on the user's own machine
(configurable via `$env:JOB_APP_TOOLKIT_HOME`; see
`job-application-toolkit/README.md`). This folder is outside the git repo
and is never committed — treat everything in it as private. It contains:

- `job-description.*` / `job-description.extracted.txt` — the JD
- `cv-source.*` / `cv-source.extracted.txt` — the candidate's real CV
- `gap-questions.md` — where you'll log unanswered requirements
- `notes.md` — deadline, referees, and other non-written requirements

If the `.extracted.txt` file is missing or empty, New-Application.ps1's own
text extraction failed — commonly a `.pdf` with no `pdftotext` installed on
the user's machine, sometimes a scanned PDF with no text layer at all.
Don't ask the user to paste text in as a first resort: try reading the
original `job-description.*` / `cv-source.*` file directly yourself first —
a `.pdf` is directly readable, a `.docx` needs the `docx` skill. Only if
that also fails (genuinely a scanned/image PDF with no text layer) ask the
user to paste the text in — never guess at content from the filename. If
there's no application folder at all and the user has just pasted a JD and
CV directly into the conversation, work from that instead; the file layout
is a convenience, not a requirement.

## Non-negotiable rules

1. **Every factual claim traces to a source.** Employer names, titles,
   dates, tools, certifications, metrics, achievements — each one must come
   from the CV text or from something the user said in this conversation or
   in `gap-questions.md`. If you can't point to where a claim came from,
   don't write it.
2. **Never inflate scope or seniority.** "Assisted with" doesn't become
   "led"; "contributed to" doesn't become "managed." Match the CV's actual
   verbs and level of ownership.
3. **Never invent numbers.** No metric in the CV and none supplied by the
   user means no number in the draft — don't estimate one into existence to
   make a bullet look stronger.
4. **Stop and ask before drafting around a gap.** When the JD lists an
   essential/required qualification the CV doesn't evidence, do not paper
   over it with vague language that sounds like a match. Add it to
   `gap-questions.md` **and** ask the user directly in the conversation.
   Wait for an answer (or an explicit "leave it out") before writing
   anything that depends on it.
5. **"I don't have that" means it's left out** — not softened, not implied
   some other way.
6. **Unmet nice-to-haves don't block drafting** — just don't claim them.
7. **No boilerplate.** Every draft should be specific enough to this one
   organization and role that it couldn't be dropped unchanged into a
   different application.

## Process

1. **Read the full JD.** Extract:
   - Role title and organization
   - Essential/required qualifications (the ones phrased as "must,"
     "required," "essential")
   - Desired/nice-to-have qualifications
   - Key responsibilities
   - Everything the application-instructions section actually asks
     candidates to submit — this is often more than "CV and cover letter":
     selection-criteria responses, a motivation/statement of interest,
     short-answer questions, referees, a portfolio or writing sample,
     salary expectation, availability date, a specific email subject
     line or file-naming format, word/page limits. NGO and INGO postings
     in particular often bury one or two of these in a paragraph rather
     than a bullet list — read the whole thing, not just the "Requirements"
     section.

2. **Read the full CV.** Build a real inventory of the candidate's actual
   experience, skills, and achievements — with the evidence for each.

3. **Build a coverage map.** For every essential qualification: Covered
   (cite the specific CV evidence) / Partially covered / Not evidenced.

4. **Surface every gap before drafting.** For each "Not evidenced"
   *essential* item, write a specific, answerable question into
   `gap-questions.md` and ask the same thing directly in chat. Example:
   > The JD asks for "experience with DHIS2 or a similar health information
   > system." I don't see this in your CV — do you have relevant
   > experience? If yes, which system(s), what did you actually do with it,
   > and roughly when/where? If no, just say so and I'll leave it out
   > rather than guess.

   Don't proceed to full drafting of sections that depend on unresolved
   essential gaps. It's fine to draft the parts that don't depend on them
   while waiting.

   There's no saved master CV to carry a gap-answer forward into — each
   application supplies its own CV file fresh. If the same real experience
   is relevant again on a future application, expect to be asked (and
   answer) again.

5. **Draft `cv-tailored.md`.** Reorder and re-emphasize real content so the
   most JD-relevant experience and bullets lead — don't invent content to
   fill gaps. Mirror the JD's own terminology only where the underlying
   fact is actually true (this genuinely helps with ATS keyword matching,
   as long as it's honest). Follow the structure in
   `job-application-toolkit/templates/cv-master-template.md`: scannable
   header, 2-3 line summary, reverse-chronological experience with
   action-verb-plus-result bullets, max 2 pages.

6. **Draft `cover-letter.md`**, structured per
   `job-application-toolkit/templates/cover-letter-template.md`, following
   the voice guide below.

7. **Draft any other written material** identified in step 1 (e.g.
   `selection-criteria.md`, one response per criterion, respecting any
   stated word limit) — same evidence-only rule, same voice guide.

8. **Ask about non-written requirements** identified in step 1 (referees,
   salary expectation, availability, portfolio links) rather than guessing.
   Record the answers in `notes.md`.

9. **Self-check every drafted paragraph against the voice guide** before
   calling it done.

10. **Hand back clearly.** Say what was drafted, what's still open (unresolved
    gaps, missing non-written info), and remind the user this is a first
    draft for them to review and personalize further — not something to
    submit unread. Mention `Export-Application.ps1` for a `.docx` copy once
    they're happy with the Markdown.

## Voice guide: read as a specific person, not "AI-cover-letter-generic"

The goal is genuine and specific, not a trick to fool a detector — a
detector-focused rewrite and a genuinely-good, specific piece of writing
converge on the same output anyway, because both come from the same fix:
say something only this candidate, about this job, could truthfully say.

**Cut these on sight:**
- Stock openers: "I am writing to express my interest in...", "I am
  excited to apply for the position of..."
- Stock closers: "I look forward to the opportunity to further discuss my
  qualifications..." (fine as a plain, short sign-off; not as a paragraph)
- Inflated vocabulary: leverage, spearhead, robust, dynamic, passionate,
  delve, furthermore, moreover, seamlessly, utilize (say "use"), showcase,
  unwavering, "in today's ever-evolving landscape"
- Structural tells: every paragraph the same length; every bullet starting
  with the same verb; reflexive rule-of-three adjective lists
  ("collaborative, innovative, and results-driven"); "not only X but also
  Y"; a sign-off that reads like it was generated to be inoffensive

**Do this instead:**
- One concrete, specific, slightly imperfect real detail per paragraph — a
  real project name, an actual number, a specific obstacle — instead of an
  abstract claim
- Vary sentence length and rhythm; short sentences are allowed
- Write it the way this person would actually say it out loud, based on how
  they write elsewhere in their own CV — match their real register instead
  of imposing a generic "professional voice"
- Let a little real opinion or specificity show
- Cut any sentence that could be pasted into literally any other
  candidate's application for any other job unchanged

**Illustrative example (not a real candidate — just to show the shift):**
- Generic: "I am a dynamic and results-driven professional with a passion
  for leveraging my skills to drive impactful change in the humanitarian
  sector."
- Specific: "I've spent the last four years running cash-transfer programs
  in Borno State — mostly the unglamorous parts: reconciling beneficiary
  lists, chasing vendor payments, explaining to a donor why a distribution
  slipped two weeks."

## Output files (inside the application folder)

- `cv-tailored.md`
- `cover-letter.md`
- any other written material the JD required, named for what it is (e.g.
  `selection-criteria.md`)
- `gap-questions.md` — updated in place, not replaced
- `notes.md` — updated with deadline/referees/etc. once known
