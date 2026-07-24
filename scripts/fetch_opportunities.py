#!/usr/bin/env python3
"""
Pulls current NGO jobs and fellowships relevant to Nigerians from public RSS
feeds and writes them to data/opportunities.json for the opportunities page.

Sources (see docs/opportunities-sources.md for why these were chosen):
  - ReliefWeb (UN OCHA): a plain RSS view of its jobs board, filtered to
    Nigeria, that needs no API key. Each item already contains the full
    job text plus a "How to apply" section with the exact application
    link, and the organization's name directly in the feed's <author>.
  - NGO Jobs in Africa: dedicated Nigeria-location feed, already scoped to
    Nigeria-based NGO/development jobs. Appears to republish some of the
    same postings as ReliefWeb, so its results are deduplicated against
    ReliefWeb's. Each item's "How to apply" section carries the exact
    application URL, and the job's own detail page carries schema.org
    hiringOrganization markup for the org's name.
  - Opportunity Desk: dedicated Fellowships feed, filtered here by keyword
    for Africa/Nigeria/global-eligibility relevance since it covers
    opportunities worldwide. Each post tags the hosting/funding
    organization as a category and links out to the specific fellowship's
    official announcement/application page.
  - Known organizations (BAMBOOHR_ORGS, SMARTRECRUITERS_ORGS,
    WORKABLE_ORGS, ORACLE_FUSION_ORGS, and the Terre des hommes/IFDC own
    RSS feeds): specific organizations that don't reliably appear in the
    three aggregators above. Queried via each org's ATS's own public API —
    the same JSON calls their career page makes in a browser, not
    scraping. Adding another organization on one of these ATS platforms is
    a config-list entry, not new code.
  - IPA and EHA Clinics: two organizations whose own career pages have no
    feed/API at all, only plain (non-JS-rendered) HTML — parsed with the
    same regex-based approach as NGO Jobs in Africa/ReliefWeb, not a
    generic connector, since each site's markup is one-off.

Every listing links to the *specific* job or fellowship page on the
organization's own site (or its official application portal) — never a
generic homepage, and never the aggregator page it was found on.

This is additive, not a full rebuild: each run loads the existing
data/opportunities.json, adds only genuinely new listings from this run's
fetch, drops anything older than MAX_AGE_DAYS (by original posting date),
then caps each type at MAX_JOBS_DISPLAYED / MAX_FELLOWSHIPS_DISPLAYED,
keeping the most recent. A listing already on the page stays there as-is
until it ages out or gets capped, even if a source's own feed stops
surfacing it (RSS feeds only show their most recent items).

No third-party dependencies: uses only the standard library so this runs in
GitHub Actions with a bare `python3` install.
"""
import html
import json
import os
import re
import ssl
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse

USER_AGENT = "NGOOpportunitiesBot/1.0 (+https://ngoopportunities.com; daily opportunities digest)"
OUTPUT_PATH = "data/opportunities.json"
MAX_PER_SOURCE = 20
PAGE_TIMEOUT = 20
MAX_AGE_DAYS = 10  # postings older than this (by original advertised date) are auto-removed at the next run
MAX_JOBS_DISPLAYED = 30
MAX_FELLOWSHIPS_DISPLAYED = 10

FELLOWSHIP_KEYWORDS = [
    "nigeria", "nigerian", "africa", "african", "sub-saharan",
    "global south", "developing countr", "all nationalities",
    "worldwide", "international applicants", "any country",
]

NON_ORG_DOMAINS = {
    "facebook.com", "twitter.com", "x.com", "instagram.com", "linkedin.com",
    "pinterest.com", "wordpress.org", "whatsapp.com", "wa.me",
    "api.whatsapp.com", "t.me", "telegram.org", "telegram.me",
    "googleapis.com", "gstatic.com", "googlesyndication.com",
    "doubleclick.net", "google.com", "youtube.com", "opportunitydesk.org",
    "ngojobsinafrica.com", "opportunitiesforafricans.com", "gmpg.org",
    "w.org", "gravatar.com", "jetpack.com", "wp.com",
    "feedburner.com", "addtoany.com", "sharethis.com", "disqus.com",
    "plus.google.com", "reddit.com", "tumblr.com", "getpocket.com",
    "flipboard.com", "mix.com", "digg.com", "vk.com", "line.me",
    "viber.com", "skype.com",
}

REGION_OR_TYPE_TAGS = {
    "africa", "america", "americas", "asia", "europe", "oceania",
    "australia and oceania", "north america", "south america", "global",
    "world", "fellowships", "scholarships", "grants", "competitions",
    "conferences", "jobs", "internships", "awards", "funding opportunities",
}

# Specific organizations that don't reliably appear in the three aggregator
# feeds above, whose ATS exposes a public API we can query directly — the
# same JSON calls the organization's own career page makes in a browser, not
# scraping. Add more by appending an entry; no new code needed per org.
BAMBOOHR_ORGS = [
    {"subdomain": "internetsociety", "name": "Internet Society"},
    {"subdomain": "precisiondev", "name": "Precision Development (PxD)"},
]

SMARTRECRUITERS_ORGS = [
    {"company_id": "SNV", "name": "SNV"},
]

WORKABLE_ORGS = [
    {"account": "nutritionintl", "name": "Nutrition International"},
]

# Oracle Fusion HCM Cloud Recruiting: {tenant}.fa.{datacenter}.oraclecloud.com
# is the pattern already seen in ReliefWeb-sourced NRC listings (a different
# tenant/datacenter). This is the same REST API the org's own public
# candidate-experience site calls to render its job search page.
ORACLE_FUSION_ORGS = [
    {"tenant": "eipn", "datacenter": "us2", "site_number": "CX_1", "name": "Catholic Relief Services (CRS)"},
]

IFDC_RELEVANCE_KEYWORDS = [
    "nigeria", "west africa", "remote", "regional", "anglophone", "global",
]

TDH_RELEVANCE_KEYWORDS = [
    "nigeria", "west africa", "remote", "home-based", "any location", "global",
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=PAGE_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_and_parse_feed(url, attempts=3, base_delay=3):
    """Fetches and parses an RSS feed, retrying with backoff on either
    step failing — a source's own feed endpoint has occasionally
    returned an empty/non-XML response to a single request (transient
    block or rate limit), which otherwise silently zeroes out that
    entire source for the run. parse_rss() must be defined below;
    Python resolves this at call time, not at module-load time."""
    last_exc = None
    for attempt in range(attempts):
        try:
            return parse_rss(fetch(url))
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                print(f"[warn] Fetch/parse attempt {attempt + 1} failed for {url}: {exc}; retrying...", file=sys.stderr)
                time.sleep(base_delay * (attempt + 1))
    raise last_exc


def has_valid_certificate(url):
    """Checks that a destination ends up on a currently-valid, encrypted
    HTTPS connection, so we never publish a link that greets visitors
    with a browser security warning or sends them over plain HTTP. Some
    sources give an http:// redirect-gateway URL as the "application
    link" (e.g. a talent-management redirect service) rather than the
    final destination — urllib follows redirects automatically, so this
    checks where it actually lands, not just the URL we were given. A
    non-cert error (timeout, 404, 405 on HEAD, etc.) doesn't fail this
    check — only landing on plain HTTP or a bad certificate does, since
    those are the failure modes that are unsafe to send people to."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=PAGE_TIMEOUT) as resp:
            final_url = resp.geturl()
        return final_url.lower().startswith("https://")
    except HTTPError as exc:
        # A non-2xx final response (e.g. 405 on HEAD) still tells us where
        # we landed — HTTPError.geturl() is the last request's URL, after
        # any redirects, so check that URL's scheme rather than assuming.
        final_url = exc.geturl() or url
        return final_url.lower().startswith("https://")
    except URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE" in str(reason).upper():
            return False
        return True
    except ssl.SSLCertVerificationError:
        return False
    except Exception:
        return True


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


ORG_STOPWORDS = {
    "founded", "is", "was", "based", "established", "working", "with",
    "for", "we", "our", "since", "a", "an", "the", "role", "operates",
    "works", "provides", "supports", "believes", "has", "have",
}


def extract_organization(content):
    """Best-effort fallback: pulls an org name out of an "About <Org>..."
    sentence when schema.org markup isn't available."""
    plain = strip_html(content)
    match = re.search(r"\bAbout\s+([A-Z][\w&.,'()/-]*(?:\s+[A-Z][\w&.,'()/-]*){0,4})", plain)
    if not match:
        return None
    words = match.group(1).strip().split()
    kept = []
    for word in words:
        if word.lower().rstrip(".,") in ORG_STOPWORDS:
            break
        kept.append(word)
    name = " ".join(kept).strip()
    return name if len(name) >= 2 else None


def is_org_domain(url):
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return False
    if netloc.startswith("www."):
        netloc = netloc[len("www."):]
    return netloc and not any(netloc == d or netloc.endswith("." + d) for d in NON_ORG_DOMAINS)


NON_PAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".zip",
)


def first_outbound_link(page_html):
    """Skips file downloads (a featured image, an application-form .docx,
    a PDF annex) even when hosted on the organization's own domain — a
    fellowship post's body can link one of these before its first real
    "apply here" link, and a direct file is never the application page
    itself. Caught in practice: an Opportunity Desk post whose featured
    image happened to be hosted on unesco.org was being kept as if it were
    the specific application page, instead of the actual article further
    down."""
    for match in re.finditer(r'href="(https?://[^"]+)"', page_html):
        url = match.group(1)
        if urlparse(url).path.lower().endswith(NON_PAGE_EXTENSIONS):
            continue
        if is_org_domain(url):
            return url
    return None


def parse_rss(raw_text):
    root = ET.fromstring(raw_text)
    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        author = (item.findtext("author") or "").strip()
        categories = [c.text.strip() for c in item.findall("category") if c.text]
        content_encoded = ""
        for child in item:
            if child.tag.endswith("encoded"):
                content_encoded = child.text or ""
        description = item.findtext("description") or ""
        items.append({
            "title": html.unescape(title),
            "link": link,
            "pub_date": pub_date,
            "author": html.unescape(author) if author else None,
            "content": content_encoded or description,
            "categories": categories,
        })
    return items


def extract_specific_apply_url(content):
    """Returns the exact application URL for this job (e.g. its Greenhouse,
    Workday, or Oracle HCM posting) from the job's own "How to apply"
    section, which ReliefWeb-style themes render as either
    "Apply here: <url>" or a bare URL on its own line."""
    section_match = re.search(r"rw-how-to-apply.*?</section>", content or "", re.DOTALL)
    if not section_match:
        return None
    url_match = re.search(r'https?://[^\s<>"]+', section_match.group(0))
    if not url_match:
        return None
    return url_match.group(0).rstrip(").,;\"'")


def extract_job_organization_name(page_html):
    """Returns the hiring organization's name from a ngojobsinafrica.com
    job page's schema.org markup, falling back to its "About <Org>" text."""
    name_match = re.search(
        r'itemprop="hiringOrganization"[^>]*>\s*<span itemprop="name">([^<]+)',
        page_html,
    )
    if name_match:
        return html.unescape(name_match.group(1)).strip()
    return extract_organization(page_html)


def extract_fellowship_org(categories):
    for tag in categories:
        normalized = tag.strip().lower()
        if normalized in REGION_OR_TYPE_TAGS:
            continue
        if " apply" in normalized or re.match(r"^[a-z0-9-]+$", normalized):
            continue
        return tag.strip()
    return None


def fetch_ngo_jobs_in_africa():
    feed_url = "https://ngojobsinafrica.com/job-location/nigeria/feed/"
    try:
        items = fetch_and_parse_feed(feed_url)
    except Exception as exc:
        print(f"[warn] NGO Jobs in Africa feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in items[:MAX_PER_SOURCE]:
        apply_url = extract_specific_apply_url(item["content"])
        if not apply_url:
            print(f"[skip] No specific application URL found for: {item['title']}", file=sys.stderr)
            continue

        if not has_valid_certificate(apply_url):
            print(f"[skip] {apply_url} has an invalid/expired certificate: {item['title']}", file=sys.stderr)
            continue

        org_name = None
        try:
            page_html = fetch(item["link"])
            org_name = extract_job_organization_name(page_html)
        except Exception as exc:
            print(f"[warn] Could not load job page {item['link']}: {exc}", file=sys.stderr)

        results.append({
            "title": item["title"],
            "organization": org_name,
            "type": "Job",
            "location": "Nigeria",
            "remote": False,
            "apply_url": apply_url,
            "posted": item["pub_date"],
        })
    return results


def extract_reliefweb_countries(description):
    """ReliefWeb tags every posting with all of its eligible countries
    (e.g. "Countries: Ethiopia, Kenya, Nigeria" for a multi-country
    regional role). Returns that list so callers can tell a Nigeria-based
    posting apart from one where Nigeria is just one of several options."""
    match = re.search(r'"tag country">\s*(?:Country|Countries):\s*([^<]+)</div>', description or "")
    if not match:
        return []
    return [c.strip() for c in match.group(1).split(",") if c.strip()]


def extract_reliefweb_apply_url(description):
    """ReliefWeb's own RSS description already contains the full job text,
    ending in a "How to apply" section (heading level varies by posting).
    Takes the first link appearing after that heading, which skips over
    any scam-warning boilerplate some organizations prepend (e.g. CARE)."""
    marker = re.search(r"how to apply", description or "", re.IGNORECASE)
    if not marker:
        return None
    tail = description[marker.start():]
    href_match = re.search(r'href="(https?://[^"]+)"', tail)
    if href_match:
        return html.unescape(href_match.group(1))
    url_match = re.search(r'https?://[^\s<>"]+', tail)
    if url_match:
        return url_match.group(0).rstrip(").,;\"'")
    return None


def fetch_reliefweb_jobs():
    """ReliefWeb (UN OCHA) publishes a plain RSS view of its jobs board,
    separate from its REST API — the API needs a pre-approved appname
    (see docs/opportunities-sources.md), but this RSS view doesn't."""
    feed_url = "https://reliefweb.int/jobs/rss.xml?" + urlencode({"search": 'country.exact:"Nigeria"'})
    try:
        items = fetch_and_parse_feed(feed_url)
    except Exception as exc:
        print(f"[warn] ReliefWeb feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in items[:MAX_PER_SOURCE]:
        apply_url = extract_reliefweb_apply_url(item["content"])
        if not apply_url:
            print(f"[skip] No specific application URL found for: {item['title']}", file=sys.stderr)
            continue

        if not has_valid_certificate(apply_url):
            print(f"[skip] {apply_url} has an invalid/expired certificate: {item['title']}", file=sys.stderr)
            continue

        countries = extract_reliefweb_countries(item["content"])
        is_nigeria_only = countries == ["Nigeria"]

        results.append({
            "title": item["title"],
            "organization": item["author"],
            "type": "Job",
            "location": "Nigeria" if is_nigeria_only else "Regional (incl. Nigeria)",
            "remote": not is_nigeria_only,
            "apply_url": apply_url,
            "posted": item["pub_date"],
        })
    return results


def fetch_opportunity_desk_fellowships():
    feed_url = "https://opportunitydesk.org/category/fellowships/feed/"
    try:
        items = fetch_and_parse_feed(feed_url)
    except Exception as exc:
        print(f"[warn] Opportunity Desk feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in items[:MAX_PER_SOURCE]:
        haystack = (item["title"] + " " + strip_html(item["content"])).lower()
        if not any(keyword in haystack for keyword in FELLOWSHIP_KEYWORDS):
            continue

        org_link = None
        try:
            page_html = fetch(item["link"])
            org_link = first_outbound_link(page_html)
        except Exception as exc:
            print(f"[warn] Could not load fellowship page {item['link']}: {exc}", file=sys.stderr)

        if not org_link:
            print(f"[skip] No organization link found for: {item['title']}", file=sys.stderr)
            continue

        if not has_valid_certificate(org_link):
            print(f"[skip] {org_link} has an invalid/expired certificate: {item['title']}", file=sys.stderr)
            continue

        results.append({
            "title": item["title"],
            "organization": extract_fellowship_org(item["categories"]),
            "type": "Fellowship",
            "location": "Remote / Varies",
            "remote": True,
            "apply_url": org_link,
            "posted": item["pub_date"],
        })
    return results


def extract_ofa_fellowship_org(title):
    """Best-effort org-name extraction from an Opportunities For Africans
    title, which reliably reads "The <Org> <...> Fellowship/Program ...".
    There's no structured org field in this feed (its category tags are
    just fragments of the title/slug, unlike Opportunity Desk's, which
    tag the actual funding org) — approximate, like extract_organization()
    elsewhere in this file."""
    text = re.sub(r"^The\s+", "", title)
    match = re.search(r"^(.+?)\s+(?:Fellowships?|Fellows|Programm?e?s?)\b", text)
    if match:
        return match.group(1).strip(" '’")
    return None


def fetch_opportunities_for_africans_fellowships():
    """Opportunities For Africans' Fellowships category — unlike Opportunity
    Desk, this whole site is already scoped to opportunities Africans can
    apply for, so no additional relevance filtering beyond the shared
    FELLOWSHIP_KEYWORDS check (kept for consistency, though it rarely
    excludes anything here). Its RSS description is just a short excerpt,
    so each item's own page is fetched for the real application link — the
    first outbound link inside its "entry-content" div, the same
    first_outbound_link() helper Opportunity Desk uses. Restricting to that
    div (rather than the whole page) matters here: this site's WordPress
    theme also emits an unrelated boilerplate link before the article body
    that would otherwise be picked up as if it were the apply link.
    Overlaps with Opportunity Desk's own fellowship postings (both have
    carried African Union/APNI fellowships identically) are caught by the
    usual dedupe() apply_url match, since this is fetched after Opportunity
    Desk in main()."""
    feed_url = "https://www.opportunitiesforafricans.com/category/fellowships/feed/"
    try:
        items = fetch_and_parse_feed(feed_url)
    except Exception as exc:
        print(f"[warn] Opportunities For Africans feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in items[:MAX_PER_SOURCE]:
        haystack = (item["title"] + " " + strip_html(item["content"])).lower()
        if not any(keyword in haystack for keyword in FELLOWSHIP_KEYWORDS):
            continue

        org_link = None
        try:
            page_html = fetch(item["link"])
            content_start = page_html.find('id="penci-post-entry-inner"')
            body_html = page_html[content_start:] if content_start != -1 else page_html
            org_link = first_outbound_link(body_html)
        except Exception as exc:
            print(f"[warn] Could not load fellowship page {item['link']}: {exc}", file=sys.stderr)

        if not org_link:
            print(f"[skip] No organization link found for: {item['title']}", file=sys.stderr)
            continue

        if not has_valid_certificate(org_link):
            print(f"[skip] {org_link} has an invalid/expired certificate: {item['title']}", file=sys.stderr)
            continue

        results.append({
            "title": item["title"],
            "organization": extract_ofa_fellowship_org(item["title"]),
            "type": "Fellowship",
            "location": "Remote / Varies",
            "remote": True,
            "apply_url": org_link,
            "posted": item["pub_date"],
        })
    return results


def classify_org_location(country_text, is_remote_flag=False):
    """Best-effort relevance/labeling for a known-organization posting,
    using whatever location signal that org's ATS provides. Returns
    (location_label, remote) if the posting is Nigeria-relevant, or None
    if it's clearly restricted to a different specific country — these
    orgs post across many countries, and most ATS location fields don't
    give us enough to know for certain, so ambiguous/missing location
    data is treated as possibly-relevant rather than excluded."""
    text = (country_text or "").strip().lower()
    if text in ("ng", "nigeria"):
        return ("Nigeria", False)
    if is_remote_flag or not text or text in ("multiple", "various", "remote", "global", "worldwide"):
        return ("Regional (incl. Nigeria)", True)
    return None


def fetch_bamboohr_jobs():
    """BambooHR's own career site is a JS app with no job data in its raw
    HTML, but it calls a public JSON endpoint to render it — the same one
    used here. https://{subdomain}.bamboohr.com/careers/{id} is BambooHR's
    standard public posting page, confirmed live for each org below."""
    results = []
    for org in BAMBOOHR_ORGS:
        url = f"https://{org['subdomain']}.bamboohr.com/careers/list"
        try:
            data = json.loads(fetch(url))
        except Exception as exc:
            print(f"[warn] BambooHR feed failed for {org['name']}: {exc}", file=sys.stderr)
            continue

        for job in data.get("result", []):
            title = (job.get("jobOpeningName") or "").strip()
            if not title:
                continue

            ats_location = job.get("atsLocation") or {}
            classification = classify_org_location(ats_location.get("country"), bool(job.get("isRemote")))
            if not classification:
                continue
            location_label, remote = classification

            apply_url = f"https://{org['subdomain']}.bamboohr.com/careers/{job['id']}"
            if not has_valid_certificate(apply_url):
                print(f"[skip] {apply_url} has an invalid/expired certificate: {title}", file=sys.stderr)
                continue

            results.append({
                "title": title,
                "organization": org["name"],
                "type": "Job",
                "location": location_label,
                "remote": remote,
                "apply_url": apply_url,
                "posted": None,  # BambooHR's list endpoint doesn't expose a posting date
            })
    return results


def fetch_smartrecruiters_jobs():
    """https://jobs.smartrecruiters.com/{company}/{id} is SmartRecruiters'
    own standard public posting page — confirmed live for each org below."""
    results = []
    for org in SMARTRECRUITERS_ORGS:
        url = f"https://api.smartrecruiters.com/v1/companies/{org['company_id']}/postings"
        try:
            data = json.loads(fetch(url))
        except Exception as exc:
            print(f"[warn] SmartRecruiters feed failed for {org['name']}: {exc}", file=sys.stderr)
            continue

        for job in data.get("content", []):
            title = (job.get("name") or "").strip()
            if not title:
                continue

            location = job.get("location") or {}
            classification = classify_org_location(location.get("country"), bool(location.get("remote")))
            if not classification:
                continue
            location_label, remote = classification

            apply_url = f"https://jobs.smartrecruiters.com/{org['company_id']}/{job['id']}"
            if not has_valid_certificate(apply_url):
                print(f"[skip] {apply_url} has an invalid/expired certificate: {title}", file=sys.stderr)
                continue

            posted = None
            released = job.get("releasedDate")
            if released:
                try:
                    posted = format_datetime(datetime.fromisoformat(released.replace("Z", "+00:00")))
                except ValueError:
                    posted = None

            results.append({
                "title": title,
                "organization": org["name"],
                "type": "Job",
                "location": location_label,
                "remote": remote,
                "apply_url": apply_url,
                "posted": posted,
            })
    return results


def fetch_tdh_jobs():
    """Terre des hommes runs its own recruiting site with a native RSS
    feed (jobs.tdh.org) — each item's own link is already the organization's
    direct application page, no extraction needed. TDH posts globally, so
    this is filtered by keyword the same way Opportunity Desk is."""
    feed_url = "https://jobs.tdh.org/en-GB/jobs.rss"
    try:
        items = fetch_and_parse_feed(feed_url)
    except Exception as exc:
        print(f"[warn] Terre des hommes feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in items[:MAX_PER_SOURCE]:
        haystack = (item["title"] + " " + strip_html(item["content"])).lower()
        if not any(keyword in haystack for keyword in TDH_RELEVANCE_KEYWORDS):
            continue

        apply_url = item["link"]
        if not has_valid_certificate(apply_url):
            print(f"[skip] {apply_url} has an invalid/expired certificate: {item['title']}", file=sys.stderr)
            continue

        is_nigeria = "nigeria" in haystack
        results.append({
            "title": item["title"],
            "organization": "Terre des hommes",
            "type": "Job",
            "location": "Nigeria" if is_nigeria else "Regional (incl. Nigeria)",
            "remote": not is_nigeria,
            "apply_url": apply_url,
            "posted": item["pub_date"],
        })
    return results


def fetch_workable_jobs():
    """Workable's own career page calls this same public JSON widget API
    — documented for public embedding, not scraping. Gives title,
    location, and a direct application_url in one call, no follow-up
    page fetch needed."""
    results = []
    for org in WORKABLE_ORGS:
        url = f"https://apply.workable.com/api/v1/widget/accounts/{org['account']}"
        try:
            data = json.loads(fetch(url))
        except Exception as exc:
            print(f"[warn] Workable feed failed for {org['name']}: {exc}", file=sys.stderr)
            continue

        for job in data.get("jobs", []):
            title = (job.get("title") or "").strip()
            if not title:
                continue

            classification = classify_org_location(job.get("country"), bool(job.get("telecommuting")))
            if not classification:
                continue
            location_label, remote = classification

            apply_url = job.get("application_url") or job.get("url")
            if not apply_url or not has_valid_certificate(apply_url):
                print(f"[skip] Invalid/missing application URL: {title}", file=sys.stderr)
                continue

            posted = None
            published_on = job.get("published_on")
            if published_on:
                try:
                    posted = format_datetime(datetime.fromisoformat(published_on).replace(tzinfo=timezone.utc))
                except ValueError:
                    posted = None

            results.append({
                "title": title,
                "organization": org["name"],
                "type": "Job",
                "location": location_label,
                "remote": remote,
                "apply_url": apply_url,
                "posted": posted,
            })
    return results


def fetch_oracle_fusion_jobs():
    """Oracle Fusion HCM Cloud Recruiting's own candidate-experience site
    calls this same REST endpoint to render its public job search page —
    the finder parameters below were reverse-engineered from that page's
    own network calls, since Oracle doesn't publish this as a stable
    documented API the way Greenhouse/Workable/SmartRecruiters do. More
    fragile than those; if a tenant stops returning results, check
    whether Oracle changed the expected finder/facet parameters."""
    results = []
    for org in ORACLE_FUSION_ORGS:
        base = f"https://{org['tenant']}.fa.{org['datacenter']}.oraclecloud.com"
        finder = (
            f"findReqs;siteNumber={org['site_number']},"
            "facetsList=LOCATIONS!WORKPLACE_TYPES!WORK_LOCATIONS!TITLES!CATEGORIES!ORGANIZATIONS!POSTING_DATES!FLEX_FIELDS,"
            "limit=50,offset=0,sortBy=POSTING_DATES_DESC"
        )
        url = (
            f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
            f"?onlyData=true&expand=requisitionList.secondaryLocations&finder={finder}"
        )
        try:
            data = json.loads(fetch(url))
            reqs = data["items"][0]["requisitionList"]
        except Exception as exc:
            print(f"[warn] Oracle Fusion feed failed for {org['name']}: {exc}", file=sys.stderr)
            continue

        for req in reqs:
            title = (req.get("Title") or "").strip()
            if not title:
                continue

            is_remote = (req.get("WorkplaceTypeCode") or "").upper() == "ORA_REMOTE"
            classification = classify_org_location(req.get("PrimaryLocationCountry"), is_remote)
            if not classification:
                continue
            location_label, remote = classification

            apply_url = f"{base}/hcmUI/CandidateExperience/en/sites/{org['site_number']}/job/{req['Id']}"
            if not has_valid_certificate(apply_url):
                print(f"[skip] {apply_url} has an invalid/expired certificate: {title}", file=sys.stderr)
                continue

            posted = None
            posted_date = req.get("PostedDate")
            if posted_date:
                try:
                    posted = format_datetime(datetime.fromisoformat(posted_date).replace(tzinfo=timezone.utc))
                except ValueError:
                    posted = None

            results.append({
                "title": title,
                "organization": org["name"],
                "type": "Job",
                "location": location_label,
                "remote": remote,
                "apply_url": apply_url,
                "posted": posted,
            })
    return results


def fetch_ifdc_jobs():
    """IFDC's SilkRoad career portal RSS. Individual job links redirect
    into an embedded widget on ifdc.org rendered client-side — the same
    situation as BambooHR/SmartRecruiters' own hosted pages not
    rendering in a plain fetch, but functioning normally for a real
    visitor's browser. IFDC posts globally, so filtered by keyword like
    Opportunity Desk/TDH."""
    feed_url = "https://jobs.silkroad.com/IFDC/Careers/rss"
    try:
        items = fetch_and_parse_feed(feed_url)
    except Exception as exc:
        print(f"[warn] IFDC feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in items[:MAX_PER_SOURCE]:
        categories = " ".join(item.get("categories") or [])
        haystack = (item["title"] + " " + categories).lower()
        if not any(keyword in haystack for keyword in IFDC_RELEVANCE_KEYWORDS):
            continue

        apply_url = item["link"]
        if not has_valid_certificate(apply_url):
            print(f"[skip] {apply_url} has an invalid/expired certificate: {item['title']}", file=sys.stderr)
            continue

        is_nigeria = "nigeria" in haystack
        results.append({
            "title": item["title"],
            "organization": "IFDC",
            "type": "Job",
            "location": "Nigeria" if is_nigeria else "Regional (incl. Nigeria)",
            "remote": not is_nigeria,
            "apply_url": apply_url,
            "posted": item["pub_date"],
        })
    return results


def fetch_ipa_jobs():
    """IPA (Innovations for Poverty Action) lists current openings in plain
    HTML on its own site — a Drupal Views listing grouped by region then
    country, not JS-rendered, but with no RSS/JSON feed to pull instead.
    Only jobs grouped under "West Africa" > "Nigeria" or under the
    "Global/Flexible Location" region are kept. Every posting's own detail
    page links out to the same ADP application instance
    (https://1.adp.com/<code>), confirmed consistent across a sample from
    every region, so that's extracted as the apply_url rather than the IPA
    page itself."""
    listing_url = "https://poverty-action.org/current-opportunities"
    try:
        page_html = fetch(listing_url)
    except Exception as exc:
        print(f"[warn] IPA listing page failed: {exc}", file=sys.stderr)
        return []

    region_blocks = dict(re.findall(r"<h1>([^<]+)</h1>(.*?)(?=<h1>|\Z)", page_html, re.DOTALL))
    job_link_re = re.compile(r'<a href="(/[^"]+)" class="link-stnd">([^<]+)')

    candidates = []  # (relative_url, title, location_label)
    global_block = region_blocks.get("Global/Flexible Location")
    if global_block:
        for href, title in job_link_re.findall(global_block):
            candidates.append((href, title, "Regional (incl. Nigeria)"))

    west_africa_block = region_blocks.get("West Africa")
    if west_africa_block:
        country_blocks = dict(re.findall(r"<h3>([^<]+)</h3>(.*?)(?=<h3>|\Z)", west_africa_block, re.DOTALL))
        nigeria_block = country_blocks.get("Nigeria")
        if nigeria_block:
            for href, title in job_link_re.findall(nigeria_block):
                candidates.append((href, title, "Nigeria"))

    results = []
    for href, title, location_label in candidates:
        title = html.unescape(title).strip()
        detail_url = "https://poverty-action.org" + href
        try:
            detail_html = fetch(detail_url)
        except Exception as exc:
            print(f"[warn] Could not load IPA job page {detail_url}: {exc}", file=sys.stderr)
            continue

        apply_match = re.search(r"https://1\.adp\.com/[A-Za-z0-9]+", detail_html)
        if not apply_match:
            print(f"[skip] No ADP application link found for: {title}", file=sys.stderr)
            continue
        apply_url = apply_match.group(0)
        if not has_valid_certificate(apply_url):
            print(f"[skip] {apply_url} has an invalid/expired certificate: {title}", file=sys.stderr)
            continue

        results.append({
            "title": title,
            "organization": "Innovations for Poverty Action (IPA)",
            "type": "Job",
            "location": location_label,
            "remote": location_label != "Nigeria",
            "apply_url": apply_url,
            "posted": None,  # no posting date is published anywhere on the listing or detail page
        })
    return results


def fetch_eha_clinics_jobs():
    """EHA Clinics runs its own Odoo-hosted careers portal at erp.eha.ng —
    unlike an aggregator, the job detail page (/jobs/detail/{slug}) is
    already the organization's own official posting, and applying happens
    through an on-page modal right there, so the detail page itself is the
    correct apply_url with no further link to extract. All current
    openings are Lagos/Abuja/Kano-based (the schema.org address on the
    listing page is EHA's registered office, not the job's own location —
    the actual city is in each job's title instead). The listing page
    conveniently carries a real publish date per posting, unlike BambooHR
    or IPA above."""
    listing_url = "https://erp.eha.ng/jobs"
    try:
        page_html = fetch(listing_url)
    except Exception as exc:
        print(f"[warn] EHA Clinics listing page failed: {exc}", file=sys.stderr)
        return []

    results = []
    entries = re.findall(
        r'<a href="(/jobs/detail/[^"]+)">\s*<span>([^<]+)</span>.*?'
        r'Publication date"[^>]*></i>\s*<span>([^<]+)</span>',
        page_html, re.DOTALL,
    )
    for href, title, posted_str in entries:
        title = html.unescape(title).strip()
        apply_url = "https://erp.eha.ng" + href
        if not has_valid_certificate(apply_url):
            print(f"[skip] {apply_url} has an invalid/expired certificate: {title}", file=sys.stderr)
            continue

        posted = None
        try:
            parsed = datetime.strptime(posted_str.strip(), "%m/%d/%Y %I:%M:%S %p").replace(tzinfo=timezone.utc)
            posted = format_datetime(parsed)
        except ValueError:
            posted = None

        results.append({
            "title": title,
            "organization": "EHA Clinics",
            "type": "Job",
            "location": "Nigeria",
            "remote": False,
            "apply_url": apply_url,
            "posted": posted,
        })
    return results


def normalize_for_dedup(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def dedupe(opportunities):
    """Keeps the first occurrence of each listing, matching on either the
    application URL or the normalized title — ReliefWeb and NGO Jobs in
    Africa sometimes carry the exact same posting (the latter appears to
    republish the former), so ReliefWeb is fetched first to win ties as
    the more authoritative, original source."""
    seen_urls = set()
    seen_titles = set()
    deduped = []
    for opp in opportunities:
        url_key = opp["apply_url"].rstrip("/").lower()
        title_key = normalize_for_dedup(opp["title"])
        if url_key in seen_urls or title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        deduped.append(opp)
    return deduped


def parse_posted_date(posted):
    try:
        parsed = parsedate_to_datetime(posted)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def stamp_missing_posted_date(opportunities):
    """Some sources (BambooHR's list endpoint, IPA, IFDC) don't expose a
    posting date at all. Without one, drop_expired() would keep an item
    forever since an unparseable date is treated as "not evidence of
    staleness" — so a first-seen listing without one gets a first_seen
    timestamp instead, the closest honest substitute, so it still ages out
    on the usual clock. This deliberately leaves "posted" itself alone
    (None/missing) rather than filling it with today's date: sort_by_recency()
    and cap_per_type() need to tell "genuinely posted today" apart from
    "we simply don't know," so a dateless listing sorts as the oldest, not
    the newest — otherwise it would permanently outrank and crowd out
    honestly-dated postings from other sources for a limited cap."""
    now_str = format_datetime(datetime.now(timezone.utc))
    for opp in opportunities:
        if not opp.get("posted") and not opp.get("first_seen"):
            opp["first_seen"] = now_str
    return opportunities


def drop_expired(opportunities, max_age_days=MAX_AGE_DAYS):
    """Drops postings older than max_age_days — likely expired or no
    longer accepting applications. Falls back to first_seen (see
    stamp_missing_posted_date()) when there's no real posted date, so a
    dateless listing still ages out on schedule instead of being kept
    forever. A posting with neither is kept rather than dropped, since
    that's a parsing gap, not evidence it's stale."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    kept = []
    dropped = 0
    for opp in opportunities:
        posted_at = parse_posted_date(opp.get("posted")) or parse_posted_date(opp.get("first_seen"))
        if posted_at is not None and posted_at < cutoff:
            dropped += 1
            continue
        kept.append(opp)
    if dropped:
        print(f"[info] Dropped {dropped} posting(s) older than {max_age_days} days", file=sys.stderr)
    return kept


def sort_by_recency(opportunities):
    """Most recent first; postings with an unparseable date sort last."""
    return sorted(
        opportunities,
        key=lambda opp: parse_posted_date(opp["posted"]) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def load_existing_opportunities():
    """Yesterday's list, so today's run can add to it instead of replacing
    it outright — a job that's scrolled out of a source's own RSS window
    (which only shows its most recent items) shouldn't disappear from our
    page just because this run's fetch didn't happen to see it again."""
    if not os.path.exists(OUTPUT_PATH):
        return []
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("opportunities", [])
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[warn] Could not read existing {OUTPUT_PATH}: {exc}", file=sys.stderr)
        return []


def merge_with_existing(existing, fresh):
    """Keeps every existing listing as-is and appends only fresh ones not
    already present (matched the same way dedupe() matches — by apply_url
    or normalized title), so a listing already on the page doesn't shift
    or get overwritten by a re-fetch of the same posting."""
    seen_urls = {opp["apply_url"].rstrip("/").lower() for opp in existing}
    seen_titles = {normalize_for_dedup(opp["title"]) for opp in existing}
    merged = list(existing)
    added = 0
    for opp in fresh:
        url_key = opp["apply_url"].rstrip("/").lower()
        title_key = normalize_for_dedup(opp["title"])
        if url_key in seen_urls or title_key in seen_titles:
            continue
        merged.append(opp)
        seen_urls.add(url_key)
        seen_titles.add(title_key)
        added += 1
    print(f"[info] {added} new opportunity(ies); {len(existing)} carried over from before this run", file=sys.stderr)
    return merged


def cap_per_type(opportunities):
    """Applied after sorting by recency, so a cap keeps the freshest ones
    of each type rather than an arbitrary cut across both types."""
    jobs = [o for o in opportunities if o["type"] == "Job"][:MAX_JOBS_DISPLAYED]
    fellowships = [o for o in opportunities if o["type"] == "Fellowship"][:MAX_FELLOWSHIPS_DISPLAYED]
    return sort_by_recency(jobs + fellowships)


def main():
    existing = load_existing_opportunities()
    fresh = dedupe(
        fetch_reliefweb_jobs()
        + fetch_ngo_jobs_in_africa()
        + fetch_opportunity_desk_fellowships()
        + fetch_opportunities_for_africans_fellowships()
        + fetch_bamboohr_jobs()
        + fetch_smartrecruiters_jobs()
        + fetch_tdh_jobs()
        + fetch_workable_jobs()
        + fetch_oracle_fusion_jobs()
        + fetch_ifdc_jobs()
        + fetch_ipa_jobs()
        + fetch_eha_clinics_jobs()
    )
    fresh = drop_expired(stamp_missing_posted_date(fresh))

    opportunities = merge_with_existing(existing, fresh)
    opportunities = drop_expired(opportunities)  # catches existing listings that just aged out since the last run
    opportunities = sort_by_recency(opportunities)
    opportunities = cap_per_type(opportunities)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(opportunities),
        "opportunities": opportunities,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Wrote {len(opportunities)} opportunities to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
