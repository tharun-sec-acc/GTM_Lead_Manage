"""Document extraction pipeline for PDF reports, financial statements, and regulatory filings.

Extracts text, metadata, table layouts, and page-level provenance using pypdf.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pypdf

logger = logging.getLogger(__name__)

MAX_DOCUMENT_BYTES = 25_000_000  # 25 MB max document budget
MAX_PAGES_TO_EXTRACT = 80        # Cap large annual reports to key/first 80 pages to avoid OOM
PDF_MAGIC_BYTES = b"%PDF-"

FINANCIAL_PATTERNS = [
    re.compile(r"\b(balance\s+sheet|statement\s+of\s+profit|income\s+statement|cash\s+flow)\b", re.I),
    re.compile(r"\b(standalone|consolidated)\s+(financial|results|statements)\b", re.I),
    re.compile(r"\b(annual\s+report|quarterly\s+results|investor\s+presentation|earnings\s+call)\b", re.I),
    re.compile(r"\b(ebitda|revenue\s+from\s+operations|net\s+profit|pbt|pat|capex)\b", re.I),
    re.compile(r"\b(crore|lakh|million|billion|inr|usd|aud|eur)\b", re.I),
]

GOVERNANCE_PATTERNS = [
    re.compile(r"\b(board\s+of\s+directors|corporate\s+governance|key\s+managerial\s+personnel)\b", re.I),
    re.compile(r"\b(managing\s+director|chief\s+executive|chief\s+financial|independent\s+director)\b", re.I),
]

OPERATIONS_PATTERNS = [
    re.compile(r"\b(manufacturing\s+facilities|warehousing|supply\s+chain|fleet\s+operations)\b", re.I),
    re.compile(r"\b(logistics\s+network|distribution\s+centres|transport\s+fleet|trucks|depots)\b", re.I),
]


@dataclass
class PageText:
    page_number: int
    text: str
    has_tables: bool = False


@dataclass
class ExtractedDocument:
    url: str
    title: str
    text: str
    pages: list[PageText] = field(default_factory=list)
    total_pages: int = 0
    extracted_pages: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    size_bytes: int = 0
    is_financial_or_regulatory: bool = False
    category: str = "document"


def is_pdf_content(content: bytes) -> bool:
    """Check if content has the standard PDF header bytes."""
    return content.startswith(PDF_MAGIC_BYTES) or (len(content) > 1024 and PDF_MAGIC_BYTES in content[:1024])


def _clean_text(text: str) -> str:
    """Normalize whitespace while preserving paragraph breaks and tabular columns."""
    if not text:
        return ""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    clean_lines = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                clean_lines.append("")
                prev_blank = True
        else:
            clean_lines.append(line)
            prev_blank = False
    return "\n".join(clean_lines).strip()


def _detect_category(title: str, full_text: str) -> tuple[str, bool]:
    sample = (title + " " + full_text[:10000]).lower()
    is_financial = any(pattern.search(sample) for pattern in FINANCIAL_PATTERNS)
    is_governance = any(pattern.search(sample) for pattern in GOVERNANCE_PATTERNS)
    is_ops = any(pattern.search(sample) for pattern in OPERATIONS_PATTERNS)

    if is_financial:
        return "financial", True
    if is_governance:
        return "leadership", False
    if is_ops:
        return "operations", False
    return "company", False


def extract_pdf_document(
    content: bytes,
    url: str,
    title: str = "",
    max_pages: int = MAX_PAGES_TO_EXTRACT,
) -> ExtractedDocument | None:
    """Extract structured text, page references, and metadata from a PDF document."""
    if not content or not is_pdf_content(content):
        logger.warning("Content for %s does not appear to be a valid PDF.", url)
        return None

    size_bytes = len(content)
    if size_bytes > MAX_DOCUMENT_BYTES:
        logger.warning("PDF %s exceeds maximum document size (%d bytes); skipping.", url, size_bytes)
        return None

    content_hash = hashlib.sha256(content).hexdigest()

    try:
        stream = io.BytesIO(content)
        reader = pypdf.PdfReader(stream, strict=False)
    except Exception as exc:
        logger.warning("Failed to parse PDF %s: %s", url, exc)
        return None

    try:
        total_pages = len(reader.pages)
    except Exception as exc:
        logger.warning("Failed to count PDF pages for %s: %s", url, exc)
        total_pages = 0

    if total_pages == 0:
        return None

    doc_meta: dict[str, Any] = {}
    try:
        raw_meta = reader.metadata
        if raw_meta:
            for k, v in raw_meta.items():
                clean_k = k.lstrip("/").lower()
                doc_meta[clean_k] = str(v)[:500] if v is not None else None
    except Exception:
        pass

    doc_title = title or doc_meta.get("title") or url.split("/")[-1].split("?")[0].replace("_", " ").replace("-", " ")
    if doc_title.lower().endswith(".pdf"):
        doc_title = doc_title[:-4].strip()

    extracted_pages: list[PageText] = []
    combined_parts: list[str] = []

    # Read up to max_pages
    pages_to_read = min(total_pages, max_pages)
    for idx in range(pages_to_read):
        page_num = idx + 1
        page_text = ""
        try:
            page = reader.pages[idx]
            # Attempt layout extraction if available in modern pypdf
            try:
                page_text = page.extract_text(extraction_mode="layout") or ""
            except TypeError:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
        except Exception:
            # Reached end of stream in truncated PDF or encountered corrupted page
            break

        clean_page = _clean_text(page_text)
        if clean_page:
            has_table = "\t" in page_text or bool(re.search(r"\d+\s{2,}\d+", page_text))
            extracted_pages.append(PageText(page_number=page_num, text=clean_page, has_tables=has_table))
            combined_parts.append(f"[Page {page_num}]\n{clean_page}")

    full_text = "\n\n".join(combined_parts)
    if not full_text.strip():
        logger.info("PDF %s contained no readable text (may be image-scanned).", url)
        return None

    category, is_financial = _detect_category(doc_title, full_text)

    return ExtractedDocument(
        url=url,
        title=doc_title,
        text=full_text,
        pages=extracted_pages,
        total_pages=total_pages,
        extracted_pages=len(extracted_pages),
        metadata=doc_meta,
        content_hash=content_hash,
        size_bytes=size_bytes,
        is_financial_or_regulatory=is_financial,
        category=category,
    )
