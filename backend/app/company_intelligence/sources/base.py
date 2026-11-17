"""Abstract base interface for research source providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SourceResult:
    """Normalized result returned by any SourceProvider."""
    url: str
    canonical_url: str
    title: str
    text: str
    content_hash: str
    category: str
    retrieval_method: str
    published_at: datetime | None = None
    excerpt: str = ""
    page_number: int | None = None
    reliability: str = "official"


class SourceProvider(ABC):
    """Abstract source retrieval interface.

    Concrete implementations: LocalHTTPProvider (website.py), BrowserProvider (browser.py).
    Future implementations: RSS, search API adapters.
    """

    @abstractmethod
    def fetch(self, url: str) -> SourceResult:
        """Fetch the resource at url and return a SourceResult.

        Raises SourceError (from website.py) on retrieval failure.
        SSRF protections must be enforced inside each implementation.
        """