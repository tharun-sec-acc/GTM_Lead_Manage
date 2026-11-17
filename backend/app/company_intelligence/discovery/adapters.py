"""Source-discovery adapters.

Every adapter returns *candidates*. Nothing here establishes a fact, and no external search
API key is required. Failures degrade to notes; they never abort a research job.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlsplit
from xml.etree import ElementTree

from app.company_intelligence.sources.website import (
    SourceError, fetch_public_text, robots_for,
)

MAX_RESOURCE_BYTES = 1_000_000
_URL_PATTERN = re.compile(r"https?://[^\s<>\"'\)\]]{8,500}")
_FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/feed+json")


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str = ""
    discovered_via: str = ""
    published_at: datetime | None = None
    snippet: str = ""


def _xml(text: str) -> ElementTree.Element:
    if "<!DOCTYPE" in text[:2000].upper():
        raise SourceError("Documents with a document type declaration are not parsed.")
    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise SourceError("The discovered document was not valid XML.") from exc


def _child_text(element: ElementTree.Element, name: str) -> str:
    for child in element:
        if child.tag.rsplit("}", 1)[-1].casefold() == name:
            return (child.text or "").strip()
    return ""


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    for parser in (
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")),
        lambda item: datetime.strptime(item, "%a, %d %b %Y %H:%M:%S %z"),
        lambda item: datetime.strptime(item, "%a, %d %b %Y %H:%M:%S %Z"),
        lambda item: datetime.strptime(item, "%Y-%m-%d"),
    ):
        try:
            parsed = parser(candidate)
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        except (ValueError, TypeError):
            continue
    return None


def _allowed(host: str, robots) -> bool:
    if robots is None:
        return True
    return robots.can_fetch("GTMProspectingResearch", f"https://{host}/")


# ---- Sitemaps ----


def _official_hosts(domain: str) -> list[str]:
    """Verified apex domains often serve their site from www only."""
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain:
        return []
    return [domain] if domain.startswith("www.") else [domain, f"www.{domain}"]


def sitemap_candidates(domain: str, deadline: float | None, limit: int,
                       notes: list[str]) -> list[Candidate]:
    hosts = _official_hosts(domain)
    sitemap_urls: list[str] = []
    for host in hosts:
        try:
            robots_text, _ = fetch_public_text(f"https://{host}/robots.txt", 131072, deadline)
            for line in robots_text.splitlines():
                key, _, value = line.partition(":")
                if key.strip().casefold() == "sitemap" and value.strip():
                    sitemap_urls.append(value.strip())
        except SourceError:
            pass
    for host in hosts:
        sitemap_urls.extend([f"https://{host}/sitemap.xml", f"https://{host}/sitemap_index.xml"])

    seen_documents: set[str] = set()
    candidates: list[Candidate] = []
    queue = list(dict.fromkeys(sitemap_urls))[:4]
    while queue and len(candidates) < limit:
        url = queue.pop(0)
        if url in seen_documents or urlsplit(url).hostname not in set(hosts):
            continue
        seen_documents.add(url)
        try:
            text, _ = fetch_public_text(url, MAX_RESOURCE_BYTES, deadline)
            root = _xml(text)
        except SourceError as exc:
            notes.append(f"Sitemap {url}: {exc}")
            continue
        locals_found = 0
        children = 0
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1].casefold() != "loc" or not (element.text or "").strip():
                continue
            loc = element.text.strip()
            if loc.lower().endswith(".xml.gz"):
                notes.append(f"Sitemap {url}: compressed sitemaps are not parsed.")
                continue
            if loc.lower().endswith(".xml") and children < 3:
                children += 1
                queue.append(loc)
                continue
            candidates.append(Candidate(url=loc, discovered_via="sitemap"))
            locals_found += 1
            if len(candidates) >= limit:
                break
        if not locals_found and not children:
            notes.append(f"Sitemap {url}: no usable URLs.")
    return candidates


def feed_candidates(domain: str, deadline: float | None, limit: int,
                    notes: list[str]) -> list[Candidate]:
    hosts = _official_hosts(domain)
    feed_urls: list[str] = []
    failures: list[str] = []
    for host in hosts:
        try:
            html, _ = fetch_public_text(f"https://{host}/", MAX_RESOURCE_BYTES, deadline)
        except SourceError as exc:
            failures.append(f"Feed discovery on {host}: {exc}")
            continue
        for match in re.finditer(r"<link\b[^>]*>", html, flags=re.IGNORECASE):
            tag = match.group(0)
            if not any(feed_type in tag.lower() for feed_type in _FEED_TYPES):
                continue
            href = re.search(r"href=[\"']([^\"']+)[\"']", tag, flags=re.IGNORECASE)
            if href and href.group(1).startswith(("http", "/")):
                feed_urls.append(href.group(1) if href.group(1).startswith("http")
                                 else f"https://{host}{href.group(1)}")
    if not feed_urls:
        notes.extend(failures[:2])
    for host in hosts:
        feed_urls.extend([
            f"https://{host}/feed", f"https://{host}/rss", f"https://{host}/rss.xml",
            f"https://{host}/feed.xml", f"https://{host}/news/feed", f"https://{host}/blog/feed",
        ])
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for url in list(dict.fromkeys(feed_urls))[:8]:
        if len(candidates) >= limit:
            break
        if url in seen:
            continue
        seen.add(url)
        try:
            text, _ = fetch_public_text(url, MAX_RESOURCE_BYTES, deadline)
            root = _xml(text)
        except SourceError:
            continue
        for entry in root.iter():
            if entry.tag.rsplit("}", 1)[-1].casefold() == "item":
                link = _child_text(entry, "link")
                candidates.append(Candidate(
                    url=link, title=_child_text(entry, "title"),
                    discovered_via="feed", published_at=_parse_date(_child_text(entry, "pubdate")),
                    snippet=_child_text(entry, "description")[:500],
                ))
            elif entry.tag.rsplit("}", 1)[-1].casefold() == "entry":
                link = ""
                for child in entry:
                    if child.tag.rsplit("}", 1)[-1].casefold() == "link":
                        link = child.attrib.get("href", "") or (child.text or "")
                        if link:
                            break
                candidates.append(Candidate(
                    url=link, title=_child_text(entry, "title"),
                    discovered_via="feed",
                    published_at=_parse_date(_child_text(entry, "published")
                                             or _child_text(entry, "updated")),
                    snippet=_child_text(entry, "summary")[:500],
                ))
            if len(candidates) >= limit:
                break
    return [candidate for candidate in candidates if candidate.url]


# ---- References and outbound links ----


def reference_candidates(texts: list[str], official_domain: str, limit: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for text in texts:
        for match in _URL_PATTERN.finditer(text or ""):
            url = match.group(0).rstrip(".,;:")
            host = (urlsplit(url).hostname or "").lower()
            if not host or host == official_domain or host == f"www.{official_domain}":
                continue
            if url in seen:
                continue
            seen.add(url)
            candidates.append(Candidate(url=url, discovered_via="document_reference"))
            if len(candidates) >= limit:
                return candidates
    return candidates


def link_candidates(links: list[str], official_domain: str, limit: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen: set[str] = set()
    for link in links:
        host = (urlsplit(link).hostname or "").lower()
        if not host or host == official_domain or host == f"www.{official_domain}":
            continue
        if link in seen:
            continue
        seen.add(link)
        candidates.append(Candidate(url=link, discovered_via="outbound_link"))
        if len(candidates) >= limit:
            break
    return candidates


# ---- Public indexes and registries (no API key) ----


def _api_allowed(url: str, deadline: float | None, notes: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    robots, robot_notes, _ = robots_for(host, deadline)
    notes.extend(robot_notes)
    allowed = robots.can_fetch("GTMProspectingResearch", url)
    if not allowed:
        notes.append(f"{host}: robots policy disallows {urlsplit(url).path or '/'}.")
    return allowed


def directory_candidates(company_name: str, deadline: float | None, limit: int,
                         notes: list[str]) -> list[Candidate]:
    """Wikipedia and Wikidata search APIs: public indexes, no credentials required."""
    candidates: list[Candidate] = []
    wikipedia_url = ("https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
                     f"{quote_plus(company_name)}&format=json&srlimit=3")
    if _api_allowed(wikipedia_url, deadline, notes):
        try:
            text, _ = fetch_public_text(wikipedia_url, MAX_RESOURCE_BYTES, deadline)
            data = json.loads(text)
            for hit in (data.get("query", {}).get("search") or [])[:3]:
                title = str(hit.get("title") or "").strip()
                if title:
                    candidates.append(Candidate(
                        url="https://en.wikipedia.org/wiki/" + quote_plus(title.replace(" ", "_")),
                        title=title, discovered_via="wikipedia_search",
                        snippet=str(hit.get("snippet") or "")[:300],
                    ))
        except (SourceError, ValueError, TypeError) as exc:
            notes.append(f"Wikipedia discovery: {exc}")

    wikidata_url = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&search="
                    f"{quote_plus(company_name)}&language=en&format=json&limit=2")
    if _api_allowed(wikidata_url, deadline, notes):
        try:
            text, _ = fetch_public_text(wikidata_url, MAX_RESOURCE_BYTES, deadline)
            data = json.loads(text)
            for item in (data.get("search") or [])[:2]:
                entity = str(item.get("id") or "")
                if entity.startswith("Q"):
                    candidates.append(Candidate(
                        url=f"https://www.wikidata.org/wiki/{entity}",
                        title=str(item.get("label") or company_name),
                        discovered_via="wikidata_search",
                        snippet=str(item.get("description") or "")[:300],
                    ))
        except (SourceError, ValueError, TypeError) as exc:
            notes.append(f"Wikidata discovery: {exc}")
    return candidates[:limit]


def sec_edgar_candidates(company_name: str, deadline: float | None, limit: int,
                         notes: list[str]) -> list[Candidate]:
    """SEC EDGAR company filings Atom feed (public, keyless)."""
    url = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company="
           f"{quote_plus(company_name)}&type=10-K&dateb=&owner=include&count=10&output=atom")
    if not _api_allowed(url, deadline, notes):
        notes.append("SEC EDGAR: robots policy disallows automated access.")
        return []
    try:
        text, _ = fetch_public_text(url, MAX_RESOURCE_BYTES, deadline)
        root = _xml(text)
    except SourceError as exc:
        notes.append(f"SEC EDGAR discovery: {exc}")
        return []
    candidates: list[Candidate] = []
    for entry in root.iter():
        if entry.tag.rsplit("}", 1)[-1].casefold() != "entry":
            continue
        link = ""
        for child in entry:
            if child.tag.rsplit("}", 1)[-1].casefold() == "link":
                link = child.attrib.get("href", "") or (child.text or "")
                if link:
                    break
        candidates.append(Candidate(
            url=link, title=_child_text(entry, "title"), discovered_via="sec_edgar",
            published_at=_parse_date(_child_text(entry, "updated")),
        ))
        if len(candidates) >= limit:
            break
    return [candidate for candidate in candidates if candidate.url]


def gleif_candidates(company_name: str, deadline: float | None, limit: int,
                     notes: list[str]) -> list[Candidate]:
    """GLEIF legal-entity registry API: keyless public regulatory records."""
    url = ("https://api.gleif.org/api/v1/lei-records?filter[entity.legalName]="
           f"{quote_plus(company_name)}&page[size]={max(1, min(limit, 5))}")
    if not _api_allowed(url, deadline, notes):
        return []
    try:
        text, _ = fetch_public_text(url, MAX_RESOURCE_BYTES, deadline)
        data = json.loads(text)
    except (SourceError, ValueError, TypeError) as exc:
        notes.append(f"GLEIF registry discovery: {exc}")
        return []
    candidates: list[Candidate] = []
    for record in (data.get("data") or [])[:limit]:
        lei = str(record.get("id") or "").strip()
        attributes = record.get("attributes") or {}
        entity = attributes.get("entity") or {}
        legal = entity.get("legalName") or {}
        if not lei:
            continue
        candidates.append(Candidate(
            url=f"https://api.gleif.org/api/v1/lei-records/{lei}",
            title=str(legal.get("name") or company_name),
            discovered_via="gleif_registry",
            snippet=str((entity.get("legalAddress") or {}).get("city") or "")[:300],
        ))
    return candidates
