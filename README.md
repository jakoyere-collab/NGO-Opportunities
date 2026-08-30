# NGO Opportunities

Landing page for the [NGO Opportunities](https://www.youtube.com/@NGO-Opportunities) career-prep YouTube channel — short videos on CVs, cover letters, interview prep, and interview simulations for NGO/development-sector job seekers.

Grew out of a WhatsApp community of 500+ members sharing NGO job opportunities.

## Structure

- `index.html` / `styles.css` — static landing page (hero, topic overview, About, link to the YouTube channel).
- `docs/content-plan.md` — the episode roadmap for the video series.
- `docs/scripts/` — example fully written video scripts.
- `job-application-toolkit/` — personal PowerShell + Claude workflow for tailoring a CV, cover letter, and other JD-required materials to one job at a time. See its own [README](job-application-toolkit/README.md).

## Running locally

This is a static site with no build step or dependencies. Open `index.html` directly in a browser, or serve it locally:

```bash
python3 -m http.server 8000
```

Then visit `http://localhost:8000`.
