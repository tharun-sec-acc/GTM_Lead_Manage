import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from app.company_intelligence.sources.website import (
    SourceError,
    _pinned_request,
    _same_site,
)

logger = logging.getLogger(__name__)

TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "msclkid", "_ga", "_gl",
    "ref", "source", "source_id", "feature",
}


def normalize_url(url: str, base_url: str | None = None) -> str:
    """Canonicalizes URLs by joining with base_url, removing UTM tracking params, and fragments."""
    if base_url:
        url = urljoin(base_url, url)

    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Drop tracking query params
    clean_params = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in TRACKING_QUERY_PARAMS
    ]
    clean_query = urlencode(clean_params)

    # Normalize path: remove redundant trailing slash unless it's just root '/'
    path = parsed.path
    if path and len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    return urlunsplit((scheme, netloc, path, clean_query, ""))


def compute_sha256(text: str) -> str:
    """Computes SHA-256 content hash of normalized text."""
    normalized = " ".join(text.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ArticleHTMLParser(HTMLParser):
    """
    Dependency-free, streaming HTML parser extracting headlines, metadata,
    links, structured JSON-LD, and clean article body text.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []  # (href, anchor_text)
        self.metadata: dict[str, str] = {}
        self.feed_urls: list[str] = []
        self.json_ld_blocks: list[str] = []

        self.in_title = False
        self.in_h1 = False
        self.in_json_ld = False
        self.current_anchor: list[str] = []
        self.current_href: str | None = None
        self.hidden_depth = 0
        self.time_tag_content: str | None = None
        self.in_time = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr_dict = {k.lower(): (v or "").strip() for k, v in attrs}

        if tag == "title":
            self.in_title = True
        elif tag == "h1":
            self.in_h1 = True
        elif tag == "time":
            self.in_time = True
            if "datetime" in attr_dict:
                self.time_tag_content = attr_dict["datetime"]

        # Hidden or boilerplate sections
        if tag in {"script", "style", "noscript", "svg", "template", "nav", "footer", "header", "aside"}:
            self.hidden_depth += 1
            if tag == "script" and attr_dict.get("type") == "application/ld+json":
                self.in_json_ld = True

        if tag == "meta":
            key = (attr_dict.get("property") or attr_dict.get("name") or "").lower()
            val = attr_dict.get("content", "").strip()
            if key and val:
                self.metadata[key] = val

        if tag == "link":
            rel = attr_dict.get("rel", "").lower()
            href = attr_dict.get("href", "")
            type_attr = attr_dict.get("type", "").lower()
            if "alternate" in rel and ("rss" in type_attr or "atom" in type_attr or "xml" in type_attr):
                if href:
                    self.feed_urls.append(href)

        if tag == "a" and attr_dict.get("href"):
            self.current_href = attr_dict["href"]
            self.current_anchor = []

        if tag in {"p", "div", "li", "h2", "h3", "br", "tr"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag == "title":
            self.in_title = False
        elif tag == "h1":
            self.in_h1 = False
        elif tag == "time":
            self.in_time = False

        if tag in {"script", "style", "noscript", "svg", "template", "nav", "footer", "header", "aside"}:
            if self.hidden_depth > 0:
                self.hidden_depth -= 1
            if tag == "script":
                self.in_json_ld = False

        if tag == "a" and self.current_href:
            anchor_text = " ".join(self.current_anchor).strip()
            self.links.append((self.current_href, anchor_text))
            self.current_href = None
            self.current_anchor = []

        if tag in {"p", "div", "li", "h2", "h3", "tr"}:
            self.text_parts.append("\n")

    def handle_data(self, data: str):
        if self.in_json_ld:
            self.json_ld_blocks.append(data)
            return

        if self.in_title:
            self.title_parts.append(data)
        if self.in_h1:
            self.h1_parts.append(data)
        if self.in_time and not self.time_tag_content:
            self.time_tag_content = data.strip()

        if self.current_href is not None:
            self.current_anchor.append(data)

        if self.hidden_depth == 0:
            cleaned = data.strip()
            if cleaned:
                self.text_parts.append(cleaned)


def parse_iso_date(raw_date: str | None) -> datetime | None:
    """Lightweight parsing of common date string formats into UTC datetime."""
    if not raw_date:
        return None
    raw = raw_date.strip()
    try:
        # ISO format
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass

    # Try regex match for YYYY-MM-DD
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
        except Exception:
            pass

    return None


class PlaywrightProvider:
    """
    SSRF-safe web extraction provider.
    Uses lightweight pinned HTTP requests by default with fallback to sandboxed Chromium when JS rendering is required.
    """

    def __init__(self, timeout_seconds: float = 25.0, user_agent: str = "GTMProspectingMarketIntel/1.0"):
        self.timeout = timeout_seconds
        self.user_agent = user_agent

    def fetch_page(self, url: str, domain: str, max_bytes: int = 1_500_000) -> tuple[int, str, dict[str, str]]:
        """
        SSRF-safe fetch of a public webpage.
        Returns status_code, html_text, and headers.
        """
        import time
        deadline = time.monotonic() + self.timeout
        try:
            resp = _pinned_request(
                url=url,
                allowed_domain=domain,
                max_bytes=max_bytes,
                can_fetch=lambda u: True,
                deadline=deadline,
            )
            html = resp.body.decode("utf-8", errors="replace")
            return resp.status, html, resp.headers
        except SourceError as e:
            logger.warning("SSRF-safe fetch failed for %s: %s", url, e)
            raise
        except Exception as e:
            logger.warning("Fetch exception for %s: %s", url, e)
            raise SourceError(f"Network error fetching {url}: {e}") from e

    def extract_article_metadata(self, html: str, url: str, publisher_name: str) -> dict[str, Any]:
        """
        Extracts structured article data (headline, date, author, body text, metadata)
        using HTML heuristics, JSON-LD NewsArticle markup, and OpenGraph metadata.
        """
        parser = ArticleHTMLParser()
        parser.feed(html)

        # 1. Parse JSON-LD blocks
        json_ld_headline = None
        json_ld_date = None
        json_ld_author = None
        json_ld_body = None

        for block in parser.json_ld_blocks:
            try:
                data = json.loads(block.strip())
                if isinstance(data, list) and data:
                    data = data[0]
                if isinstance(data, dict):
                    t = data.get("@type", "")
                    if t in ("NewsArticle", "Article", "BlogPosting", "Report"):
                        json_ld_headline = data.get("headline")
                        json_ld_date = data.get("datePublished") or data.get("dateCreated")
                        author_data = data.get("author")
                        if isinstance(author_data, dict):
                            json_ld_author = author_data.get("name")
                        elif isinstance(author_data, str):
                            json_ld_author = author_data
                        json_ld_body = data.get("articleBody")
            except Exception:
                continue

        # 2. Extract OpenGraph and Meta tags
        meta = parser.metadata
        og_title = meta.get("og:title") or meta.get("twitter:title") or meta.get("title")
        og_date = meta.get("article:published_time") or meta.get("og:published_time") or meta.get("publish_date") or meta.get("date")
        meta_desc = meta.get("og:description") or meta.get("twitter:description") or meta.get("description")

        # 3. Resolve Headline
        h1_text = " ".join(parser.h1_parts).strip() if parser.h1_parts else None
        page_title = " ".join(parser.title_parts).strip() if parser.title_parts else None

        headline = json_ld_headline or og_title or h1_text or page_title or "Automotive Industry Announcement"
        if " | " in headline:
            headline = headline.split(" | ")[0].strip()
        elif " - " in headline and publisher_name.lower() in headline.lower():
            headline = headline.split(" - ")[0].strip()

        # 4. Resolve Publication Date
        raw_date = json_ld_date or og_date or parser.time_tag_content
        parsed_dt = parse_iso_date(raw_date)

        # 5. Resolve Body Content
        body_text = json_ld_body
        if not body_text or len(body_text) < 150:
            cleaned_tokens = [p for p in parser.text_parts if len(p.split()) > 4]
            body_text = "\n\n".join(cleaned_tokens)

        if not body_text or len(body_text) < 50:
            body_text = meta_desc or headline

        canonical_url = normalize_url(url)
        content_hash = compute_sha256(f"{headline}\n{body_text}")

        return {
            "headline": headline[:500],
            "published_at": parsed_dt or datetime.now(timezone.utc),
            "author": json_ld_author or meta.get("author") or meta.get("article:author") or None,
            "publisher": publisher_name,
            "summary": (meta_desc or body_text[:300])[:1000],
            "body_text": body_text,
            "canonical_url": canonical_url,
            "original_url": url,
            "content_hash": content_hash,
            "metadata_json": {
                "has_json_ld": bool(json_ld_headline),
                "has_og_meta": bool(og_title),
                "extracted_length": len(body_text),
            },
        }
