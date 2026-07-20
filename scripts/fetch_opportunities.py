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
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.error import URLError
from urllib.parse import urlencode, urlparse

USER_AGENT = "NGOOpportunitiesBot/1.0 (+https://ngoopportunities.com; daily opportunities digest)"
OUTPUT_PATH = "data/opportunities.json"
MAX_PER_SOURCE = 20
PAGE_TIMEOUT = 20
MAX_AGE_DAYS = 10  # postings older than this (by original advertised date) are auto-removed at the next run
MAX_JOBS_DISPLAYED = 20
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
    "ngojobsinafrica.com", "w.org", "gravatar.com", "jetpack.com", "wp.com",
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


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=PAGE_TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def has_valid_certificate(url):
    """Checks that an https:// destination presents a currently-valid TLS
    certificate, so we never publish a link that greets visitors with a
    browser security warning. A non-cert error (timeout, 404, 405 on HEAD,
    etc.) doesn't fail this check — only certificate problems do, since
    those are the one failure mode that's unsafe to send people to."""
    if not url.lower().startswith("https://"):
        return True
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        urllib.request.urlopen(req, timeout=PAGE_TIMEOUT)
        return True
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


def first_outbound_link(page_html):
    for match in re.finditer(r'href="(https?://[^"]+)"', page_html):
        url = match.group(1)
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
        items = parse_rss(fetch(feed_url))
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
        items = parse_rss(fetch(feed_url))
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
        items = parse_rss(fetch(feed_url))
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


def drop_expired(opportunities, max_age_days=MAX_AGE_DAYS):
    """Drops postings older than max_age_days — likely expired or no
    longer accepting applications. A posting with an unparseable date is
    kept rather than dropped, since that's a parsing gap, not evidence
    it's stale."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    kept = []
    dropped = 0
    for opp in opportunities:
        posted_at = parse_posted_date(opp["posted"])
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
    fresh = drop_expired(dedupe(
        fetch_reliefweb_jobs()
        + fetch_ngo_jobs_in_africa()
        + fetch_opportunity_desk_fellowships()
    ))

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
