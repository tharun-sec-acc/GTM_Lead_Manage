import logging
from typing import Any
from urllib.parse import urljoin, urlsplit
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.market_intelligence.models import MarketSource
from app.market_intelligence.providers.playwright_provider import ArticleHTMLParser, PlaywrightProvider, normalize_url
from app.company_intelligence.sources.website import SourceError, _same_site

logger = logging.getLogger(__name__)

NEWS_KEYWORDS = [
    "news", "press-release", "press-releases", "announcements",
    "media", "media-centre", "updates", "latest-news", "corporate-news",
    "investors/news", "blog", "articles", "newsroom", "insights",
]

COMMON_NEWS_PATHS = [
    "/news", "/press-releases", "/press", "/media", "/newsroom",
    "/media-releases", "/announcements", "/latest-news", "/company/news",
]


class SourceDiscoveryService:
    def __init__(self, provider: PlaywrightProvider | None = None):
        self.provider = provider or PlaywrightProvider(timeout_seconds=20.0)

    def discover_source_sections(self, session: Session, source_id: str) -> dict[str, Any]:
        """
        Visits the homepage of a source, discovers actual news/media/press-release sections,
        checks for exposed feeds or sitemaps, validates responsiveness, and updates the registry.
        """
        source = session.get(MarketSource, source_id)
        if not source:
            raise ValueError(f"MarketSource {source_id} not found")

        homepage = source.homepage_url
        domain = source.domain
        logger.info("Discovering news sections for source '%s' (%s)", source.name, domain)

        discovered_news_url = None
        discovered_feed_url = None
        validation_status = "failed"
        last_error = None

        try:
            status, html, headers = self.provider.fetch_page(homepage, domain)
            if status < 400:
                parser = ArticleHTMLParser()
                parser.feed(html)

                # 1. Discover RSS/Atom feed links in <head>
                if parser.feed_urls:
                    discovered_feed_url = normalize_url(parser.feed_urls[0], base_url=homepage)

                # 2. Inspect navigation and anchors on homepage
                candidate_urls: list[tuple[int, str]] = []  # (priority_weight, url)

                for href, anchor_text in parser.links:
                    href = href.strip()
                    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                        continue

                    full_url = normalize_url(href, base_url=homepage)
                    parsed = urlsplit(full_url)

                    # Ensure same-site
                    if not _same_site(parsed.hostname or "", domain):
                        continue

                    path = parsed.path.lower()
                    text = anchor_text.lower()

                    # Match against news keywords
                    weight = 0
                    for kw in NEWS_KEYWORDS:
                        if f"/{kw}" in path or path.endswith(f"/{kw}"):
                            weight += 10
                        if kw in text:
                            weight += 5

                    if weight > 0:
                        candidate_urls.append((weight, full_url))

                # Sort candidates by weight
                candidate_urls.sort(key=lambda x: x[0], reverse=True)

                # Validate top candidate
                if candidate_urls:
                    best_url = candidate_urls[0][1]
                    try:
                        c_status, _, _ = self.provider.fetch_page(best_url, domain)
                        if c_status < 400:
                            discovered_news_url = best_url
                            validation_status = "validated"
                    except Exception as e:
                        logger.warning("Top news candidate %s failed validation: %s", best_url, e)

                # If no link on homepage, test common paths
                if not discovered_news_url:
                    for cp in COMMON_NEWS_PATHS:
                        test_url = urljoin(homepage, cp)
                        try:
                            t_status, _, _ = self.provider.fetch_page(test_url, domain)
                            if t_status < 400:
                                discovered_news_url = test_url
                                validation_status = "validated"
                                break
                        except Exception:
                            continue

                if not discovered_news_url:
                    # Homepage itself serves news (common for ET Auto, Autocar Pro, ITLN)
                    discovered_news_url = homepage
                    validation_status = "validated"

            else:
                last_error = f"HTTP {status} returned by homepage"

        except SourceError as e:
            last_error = str(e)
            validation_status = "restricted" if "denied" in str(e).lower() else "failed"
        except Exception as e:
            last_error = f"Discovery error: {e}"
            validation_status = "failed"

        # Update source
        source.discovered_news_url = discovered_news_url
        source.discovered_feed_url = discovered_feed_url
        source.validation_status = validation_status
        source.last_error = last_error
        session.commit()

        return {
            "source_id": source.id,
            "domain": source.domain,
            "discovered_news_url": discovered_news_url,
            "discovered_feed_url": discovered_feed_url,
            "validation_status": validation_status,
            "last_error": last_error,
        }
