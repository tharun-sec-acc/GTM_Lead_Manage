import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.market_intelligence.models import (
    MarketSource,
    MarketSourceRun,
    MarketArticle,
    MarketArticleVersion,
    now,
)
from app.market_intelligence.providers.playwright_provider import (
    ArticleHTMLParser,
    PlaywrightProvider,
    normalize_url,
)
from app.company_intelligence.sources.website import SourceError, _same_site

logger = logging.getLogger(__name__)

ARTICLE_PATH_PATTERNS = [
    r"/news/[a-zA-Z0-9_\-]+",
    r"/story/[a-zA-Z0-9_\-]+",
    r"/article/[a-zA-Z0-9_\-]+",
    r"/press-release/[a-zA-Z0-9_\-]+",
    r"/post/[a-zA-Z0-9_\-]+",
    r"/[0-9]{4}/[0-9]{2}/",  # date-based slugs like /2026/11/...
    r"/[a-zA-Z0-9_\-]+\.html",
]

EXCLUDE_PATTERNS = [
    r"/(tag|category|author|page|search|login|signin|register|privacy|terms|contact|about|careers)/",
    r"\.(pdf|jpg|jpeg|png|gif|zip|exe|mp4|mp3|svg)$",
]


class CrawlService:
    def __init__(self, provider: PlaywrightProvider | None = None):
        self.provider = provider or PlaywrightProvider(timeout_seconds=25.0)

    def is_likely_article_url(self, url: str, base_domain: str) -> bool:
        """Determines if a URL is likely an individual news article rather than an index or utility page."""
        parsed = urlsplit(url)
        if not _same_site(parsed.hostname or "", base_domain):
            return False

        path = parsed.path.lower()
        if path in ("", "/"):
            return False

        # Exclude common non-article paths
        for ep in EXCLUDE_PATTERNS:
            if re.search(ep, path):
                return False

        # Check positive patterns
        for ap in ARTICLE_PATH_PATTERNS:
            if re.search(ap, path):
                return True

        # Fallback: if path has segments and slug is long enough (>18 chars) and contains hyphen
        parts = [p for p in path.split("/") if p]
        if parts and len(parts[-1]) >= 18 and "-" in parts[-1]:
            return True

        return False

    def crawl_source(self, session: Session, source_id: str, max_articles: int = 15) -> dict[str, Any]:
        """
        Crawls a source's news listing, discovers new articles, extracts body and metadata,
        deduplicates against stored articles via canonical URLs and SHA-256 hashes.
        """
        source = session.get(MarketSource, source_id)
        if not source:
            raise ValueError(f"MarketSource {source_id} not found")

        # Create Run record
        run = MarketSourceRun(
            source_id=source.id,
            run_type="scheduled",
            status="running",
            started_at=now(),
        )
        session.add(run)
        session.commit()

        target_url = source.discovered_news_url or source.homepage_url
        logger.info("Starting crawl for '%s' at %s", source.name, target_url)

        discovered_urls: list[str] = []
        new_articles_count = 0
        updated_articles_count = 0
        error_summary = None

        try:
            status, html, _ = self.provider.fetch_page(target_url, source.domain)
            if status >= 400:
                raise SourceError(f"HTTP {status} returned by news listing")

            parser = ArticleHTMLParser()
            parser.feed(html)

            # Extract all candidate links
            raw_links: set[str] = set()
            for href, _ in parser.links:
                href = href.strip()
                if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                    continue
                full_url = normalize_url(href, base_url=target_url)
                if self.is_likely_article_url(full_url, source.domain):
                    raw_links.add(full_url)

            discovered_urls = list(raw_links)
            logger.info("Discovered %d candidate article links on '%s'", len(discovered_urls), source.name)

            # Process candidates up to max_articles limit
            for article_url in discovered_urls[:max_articles]:
                try:
                    canonical = normalize_url(article_url)
                    existing_article = session.scalar(
                        select(MarketArticle).where(MarketArticle.canonical_url == canonical)
                    )

                    # Fetch article content
                    time.sleep(0.5)  # polite domain delay
                    a_status, a_html, _ = self.provider.fetch_page(article_url, source.domain)
                    if a_status >= 400:
                        continue

                    metadata = self.provider.extract_article_metadata(a_html, article_url, publisher_name=source.name)
                    content_hash = metadata["content_hash"]

                    if not existing_article:
                        # New article
                        article = MarketArticle(
                            source_id=source.id,
                            headline=metadata["headline"],
                            original_url=article_url,
                            canonical_url=canonical,
                            publisher=source.name,
                            author=metadata.get("author"),
                            published_at=metadata.get("published_at"),
                            summary=metadata.get("summary"),
                            body_text=metadata.get("body_text"),
                            content_hash=content_hash,
                            extraction_status="extracted",
                            ai_processed=False,
                            metadata_json=metadata.get("metadata_json", {}),
                        )
                        session.add(article)
                        session.flush()

                        version = MarketArticleVersion(
                            article_id=article.id,
                            version_number=1,
                            content_hash=content_hash,
                            headline=metadata["headline"],
                            body_text=metadata.get("body_text"),
                            diff_summary="Initial extraction",
                        )
                        session.add(version)
                        new_articles_count += 1
                        session.commit()

                    else:
                        # Check for material content update
                        if existing_article.content_hash != content_hash:
                            old_len = len(existing_article.body_text or "")
                            new_len = len(metadata.get("body_text") or "")
                            # If size differs by more than 100 chars, treat as material change
                            if abs(old_len - new_len) > 100 or old_len == 0:
                                next_v = existing_article.version_count + 1
                                existing_article.version_count = next_v
                                existing_article.content_hash = content_hash
                                existing_article.body_text = metadata.get("body_text")
                                existing_article.headline = metadata["headline"]
                                existing_article.ai_processed = False  # trigger re-analysis

                                ver = MarketArticleVersion(
                                    article_id=existing_article.id,
                                    version_number=next_v,
                                    content_hash=content_hash,
                                    headline=metadata["headline"],
                                    body_text=metadata.get("body_text"),
                                    diff_summary=f"Material content update (length change: {old_len} -> {new_len})",
                                )
                                session.add(ver)
                                updated_articles_count += 1
                                session.commit()

                except Exception as ae:
                    logger.warning("Error processing article %s: %s", article_url, ae)
                    continue

            # Update Source & Run status
            source.last_crawl_at = now()
            source.last_success_at = now()
            source.articles_discovered += len(discovered_urls)
            source.articles_processed += new_articles_count
            if new_articles_count > 0:
                source.last_article_at = now()
            source.validation_status = "validated"

            run.status = "completed"
            run.articles_discovered = len(discovered_urls)
            run.articles_extracted = new_articles_count
            run.finished_at = now()
            run.details = {
                "discovered_links": len(discovered_urls),
                "new_articles": new_articles_count,
                "updated_articles": updated_articles_count,
            }
            session.commit()

        except Exception as e:
            error_summary = str(e)
            logger.error("Crawl failed for source '%s': %s", source.name, e)
            source.failed_requests += 1
            source.last_error = error_summary
            run.status = "failed"
            run.error_summary = error_summary
            run.finished_at = now()
            session.commit()

        return {
            "source_id": source.id,
            "source_name": source.name,
            "status": run.status,
            "articles_discovered": len(discovered_urls),
            "new_articles": new_articles_count,
            "updated_articles": updated_articles_count,
            "error_summary": error_summary,
        }
