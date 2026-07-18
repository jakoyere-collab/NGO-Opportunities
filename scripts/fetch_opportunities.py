#!/usr/bin/env python3
"""
Pulls current NGO jobs and fellowships relevant to Nigerians from public RSS
feeds and writes them to data/opportunities.json for the opportunities page.

Sources (see docs/opportunities-sources.md for why these were chosen):
  - NGO Jobs in Africa: dedicated Nigeria-location feed, already scoped to
    Nigeria-based NGO/development jobs. Each job's own page carries
    schema.org hiringOrganization markup and a "Connect with us on Website"
    link straight to the hiring organization's own homepage.
  - Opportunity Desk: dedicated Fellowships feed, filtered here by keyword
    for Africa/Nigeria/global-eligibility relevance since it covers
    opportunities worldwide. Each post tags the hosting/funding
    organization as a category and links out to its official portal.

Every listing links to the organization's own site (or its official
application portal), never to the aggregator page it was found on.

No third-party dependencies: uses only the standard library so this runs in
GitHub Actions with a bare `python3` install.
"""
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlparse

USER_AGENT = "NGOOpportunitiesBot/1.0 (+https://ngoopportunities.com; daily opportunities digest)"
OUTPUT_PATH = "data/opportunities.json"
MAX_PER_SOURCE = 20
PAGE_TIMEOUT = 20

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


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


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
            "content": content_encoded or description,
            "categories": categories,
        })
    return items


def extract_apply_here(content):
    match = re.search(r"Apply here:\s*(\S+)", content or "")
    if not match:
        return None
    url = match.group(1).split("<", 1)[0]
    return url.rstrip(").,;\"'")


def extract_job_org_details(page_html):
    """Returns (organization_name, organization_website) from a
    ngojobsinafrica.com job page using its schema.org + profile-widget markup."""
    org_name = None
    name_match = re.search(
        r'itemprop="hiringOrganization"[^>]*>\s*<span itemprop="name">([^<]+)',
        page_html,
    )
    if name_match:
        org_name = html.unescape(name_match.group(1)).strip()

    org_site = None
    site_match = re.search(
        r'title="Connect with us on Website"[^>]*href="([^"]+)"',
        page_html,
    )
    if site_match:
        org_site = site_match.group(1).strip()

    return org_name, org_site


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
        raw = fetch(feed_url)
    except Exception as exc:
        print(f"[warn] NGO Jobs in Africa feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in parse_rss(raw)[:MAX_PER_SOURCE]:
        org_name, org_site = None, None
        try:
            page_html = fetch(item["link"])
            org_name, org_site = extract_job_org_details(page_html)
        except Exception as exc:
            print(f"[warn] Could not load job page {item['link']}: {exc}", file=sys.stderr)

        apply_url = org_site or extract_apply_here(item["content"])
        if not apply_url:
            print(f"[skip] No organization link found for: {item['title']}", file=sys.stderr)
            continue

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


def fetch_opportunity_desk_fellowships():
    feed_url = "https://opportunitydesk.org/category/fellowships/feed/"
    try:
        raw = fetch(feed_url)
    except Exception as exc:
        print(f"[warn] Opportunity Desk feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in parse_rss(raw)[:MAX_PER_SOURCE]:
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


def main():
    opportunities = fetch_ngo_jobs_in_africa() + fetch_opportunity_desk_fellowships()

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
