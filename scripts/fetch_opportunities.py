#!/usr/bin/env python3
"""
Pulls current NGO jobs and fellowships relevant to Nigerians from public RSS
feeds and writes them to data/opportunities.json for the opportunities page.

Sources (see docs/opportunities-sources.md for why these were chosen):
  - NGO Jobs in Africa: dedicated Nigeria-location feed, already scoped to
    Nigeria-based NGO/development jobs. The feed content includes a
    "How to apply" line with the original organization's application link.
  - Opportunity Desk: dedicated Fellowships feed, filtered here by keyword
    for Africa/Nigeria/global-eligibility relevance since it covers
    opportunities worldwide.

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

USER_AGENT = "NGOOpportunitiesBot/1.0 (+https://ngoopportunities.com; daily opportunities digest)"
OUTPUT_PATH = "data/opportunities.json"
MAX_PER_SOURCE = 20

FELLOWSHIP_KEYWORDS = [
    "nigeria", "nigerian", "africa", "african", "sub-saharan",
    "global south", "developing countr", "all nationalities",
    "worldwide", "international applicants", "any country",
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


ORG_STOPWORDS = {
    "founded", "is", "was", "based", "established", "working", "with",
    "for", "we", "our", "since", "a", "an", "the", "role", "operates",
    "works", "provides", "supports", "believes", "has", "have",
}


def extract_apply_url(content, fallback_url):
    match = re.search(r"Apply here:\s*(\S+)", content or "")
    if match:
        url = match.group(1)
        url = url.split("<", 1)[0]  # drop any trailing HTML like </p>
        return url.rstrip(").,;\"'")
    return fallback_url


def extract_organization(content):
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
    if len(name) < 2:
        return None
    return name


def parse_rss(raw_bytes):
    root = ET.fromstring(raw_bytes)
    items = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
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
        })
    return items


def fetch_ngo_jobs_in_africa():
    url = "https://ngojobsinafrica.com/job-location/nigeria/feed/"
    try:
        raw = fetch(url)
    except Exception as exc:
        print(f"[warn] NGO Jobs in Africa feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in parse_rss(raw)[:MAX_PER_SOURCE]:
        results.append({
            "title": item["title"],
            "organization": extract_organization(item["content"]),
            "type": "Job",
            "location": "Nigeria",
            "remote": False,
            "source": "NGO Jobs in Africa",
            "source_url": "https://ngojobsinafrica.com/job-location/nigeria/",
            "apply_url": extract_apply_url(item["content"], item["link"]),
            "posted": item["pub_date"],
        })
    return results


def fetch_opportunity_desk_fellowships():
    url = "https://opportunitydesk.org/category/fellowships/feed/"
    try:
        raw = fetch(url)
    except Exception as exc:
        print(f"[warn] Opportunity Desk feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in parse_rss(raw)[:MAX_PER_SOURCE]:
        haystack = (item["title"] + " " + strip_html(item["content"])).lower()
        if not any(keyword in haystack for keyword in FELLOWSHIP_KEYWORDS):
            continue
        results.append({
            "title": item["title"],
            "organization": None,
            "type": "Fellowship",
            "location": "Remote / Varies",
            "remote": True,
            "source": "Opportunity Desk",
            "source_url": "https://opportunitydesk.org/category/fellowships/",
            "apply_url": item["link"],
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
