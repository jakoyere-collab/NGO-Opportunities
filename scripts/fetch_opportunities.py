#!/usr/bin/env python3
"""
Pulls current NGO jobs and fellowships relevant to Nigerians from public RSS
feeds and writes them to data/opportunities.json for the opportunities page.

Sources (see docs/opportunities-sources.md for why these were chosen):
  - NGO Jobs in Africa: dedicated Nigeria-location feed, already scoped to
    Nigeria-based NGO/development jobs. Each item's "How to apply" section
    carries the exact application URL for that specific posting (its
    Greenhouse/Workday/Oracle HCM job page), and the job's own detail page
    carries schema.org hiringOrganization markup for the org's name.
  - Opportunity Desk: dedicated Fellowships feed, filtered here by keyword
    for Africa/Nigeria/global-eligibility relevance since it covers
    opportunities worldwide. Each post tags the hosting/funding
    organization as a category and links out to the specific fellowship's
    official announcement/application page.

Every listing links to the *specific* job or fellowship page on the
organization's own site (or its official application portal) — never a
generic homepage, and never the aggregator page it was found on.

No third-party dependencies: uses only the standard library so this runs in
GitHub Actions with a bare `python3` install.
"""
import html
import json
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.error import URLError
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
        raw = fetch(feed_url)
    except Exception as exc:
        print(f"[warn] NGO Jobs in Africa feed failed: {exc}", file=sys.stderr)
        return []

    results = []
    for item in parse_rss(raw)[:MAX_PER_SOURCE]:
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
