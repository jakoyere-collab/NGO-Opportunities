# Opportunities Feed — Sources & Automation

`data/opportunities.json` powers the **See Current Opportunities** page. It's regenerated daily by `.github/workflows/update-opportunities.yml`, which runs `scripts/fetch_opportunities.py` and commits the result if anything changed.

## Current sources

| Source | What it covers | Why this one |
|---|---|---|
| [NGO Jobs in Africa — Nigeria feed](https://ngojobsinafrica.com/job-location/nigeria/feed/) | NGO/development jobs physically based in Nigeria | Official RSS feed already scoped to Nigeria, permitted by `robots.txt`. Each item's own "How to apply" section names the exact application URL for that specific posting (its Greenhouse/Workday/Oracle HCM job page — the organization's own career-site listing, not its homepage), and the job's detail page carries schema.org `hiringOrganization` markup for the org's name. |
| [Opportunity Desk — Fellowships category feed](https://opportunitydesk.org/category/fellowships/feed/) | Global fellowships, filtered here to ones mentioning Nigeria/Africa/global eligibility | Official RSS feed, but covers fellowships worldwide, so the script keeps only items whose title/description mention Nigeria, Africa, or open/global eligibility. The hosting/funding organization is read from the post's own category tags (e.g. "Africa CDC", "University of Oslo"), and the listing links to the first outbound link on the org's own post — which in practice is the specific fellowship's own announcement/application page (e.g. a listing on the African Union's or the university's own careers portal), not a generic homepage. |

Both are pulled via plain RSS + a single follow-up page fetch per item (`urllib` + regex, no scraping framework, no headless browser, no third-party dependencies) — this is what these feeds are published for.

**Every listing links to the *specific* job or fellowship page on the organization's own site or official application portal — never a generic homepage, and never the aggregator page it was found on.** If a posting doesn't yield a specific application URL, it's dropped from the feed rather than falling back to something less precise (see `[skip]` lines in the workflow logs). This also filters out Opportunity Desk's periodic "N opportunities currently open" round-up posts, since those don't point to a single organization.

**Trade-off:** many NGO Jobs in Africa postings don't include an external application link at all — they collect applications through their own on-site form instead of forwarding to the organization's career site. Those get dropped too, since there's nothing to link to that meets the "exact org page" requirement. In practice this can cut a day's job count roughly in half or more; it trades volume for every remaining listing being precise.

## Sites considered but not automated (yet)

- **ReliefWeb** (reliefweb.int) — the best source for UN/humanitarian jobs in Nigeria, including remote/consultancy roles, with a real API. However, as of late 2025 the API requires a **pre-approved `appname`** (submitted via https://apidoc.reliefweb.int/parameters#appname) — this can't be obtained programmatically, someone has to fill out the request form. Once approved, add the appname as a GitHub Actions secret (`RELIEFWEB_APPNAME`) and extend `fetch_opportunities.py` with a `fetch_reliefweb()` function following the same pattern as the other two.
- **MyJobMag** and **HotNigerianJobs** — large, popular Nigerian job boards with sizeable NGO categories, but neither publishes an RSS feed for that category, so pulling them means scraping HTML pages directly. Their `robots.txt` doesn't block the listing pages, but HTML scraping is more fragile (breaks silently when the site's markup changes) and sits in more of a legal gray area than an official feed. Worth adding later if the RSS-based sources aren't enough volume, ideally with rate limiting and a clear User-Agent identifying the bot.

## Eligibility caveat

"Eligible for Nigerians" is not a field either source exposes directly. The NGO Jobs in Africa feed is scoped by *location* (jobs based in Nigeria), which is a reliable proxy. The Opportunity Desk fellowships feed is filtered by *keyword match* against Nigeria/Africa/global-eligibility terms, which is a heuristic — it can both miss genuinely open opportunities that don't use those exact words, and occasionally include one that turns out to be region-restricted elsewhere in the fine print. Always read the "Eligibility" section on the original posting before applying.

## Extending the pipeline

To add a new source:
1. Write a `fetch_<source>()` function in `scripts/fetch_opportunities.py` returning a list of dicts with the same shape as the existing ones (`title`, `organization`, `type`, `location`, `remote`, `apply_url`, `posted`), where `apply_url` is the organization's own site or official application portal — not the aggregator's page.
2. Add its results to the list built in `main()`.
3. If it needs credentials (like a ReliefWeb appname), read them from an environment variable and pass the corresponding GitHub Actions secret through the workflow's `env:`.
