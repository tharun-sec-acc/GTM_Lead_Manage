"""Deterministic discovery-query expansion.

Queries are leads to sources, never factual evidence. They are generated from the company
identifiers already stored on the research profile and the supplied research categories.
"""

import re
from dataclasses import dataclass

MAX_QUERIES = 120

CATEGORY_TEMPLATES: dict[str, tuple[str, ...]] = {
    "company": (
        "{name} company profile",
        "{name} subsidiaries",
        "{name} product portfolio",
        "{name} business model",
        "{name} history",
    ),
    "financial": (
        "{name} annual report",
        "{name} annual report pdf",
        "{name} financial results",
        "{name} investor relations",
        "{name} revenue",
    ),
    "funding": (
        "{name} acquisitions",
        "{name} funding",
        "{name} investment",
    ),
    "leadership": (
        "{name} leadership",
        "{name} chief executive officer",
        "{name} board of directors",
    ),
    "competitors": (
        "{name} competitors",
        "{name} market position",
        "{name} industry news",
    ),
    "signals": (
        "{name} digital transformation",
        "{name} technology strategy",
        "{name} manufacturing facilities",
        "{name} expansion",
    ),
    "news": (
        "{name} news",
        "{name} press release",
    ),
}

SUBSIDIARY_TEMPLATES = (
    "{value} annual report",
    "{value} company profile",
    "{value} news",
)
BRAND_TEMPLATES = ("{value} brand", "{value} product")
PRODUCT_TEMPLATES = ("{value} product", "{value} technology")
FORMER_TEMPLATES = ("{value} former company", "{value} news")
LEADER_TEMPLATES = ("{value} {name}", "{value} interview")
COMPETITOR_TEMPLATES = ("{value} market", "{value} comparison")
INDUSTRY_TEMPLATES = ("{name} {value}", "{value} industry news")
COUNTRY_TEMPLATES = ("{name} {value}", "{name} operations {value}")

_REGISTRY_TEMPLATES = ("{name} regulatory filings", "{name} company registry")


@dataclass(frozen=True)
class DiscoveryQuery:
    text: str
    category: str


def _clean(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", text.casefold())}


def expand_queries(
    company_name: str,
    *,
    domain: str | None = None,
    subsidiaries: tuple[str, ...] | list[str] = (),
    brands: tuple[str, ...] | list[str] = (),
    products: tuple[str, ...] | list[str] = (),
    former_names: tuple[str, ...] | list[str] = (),
    leaders: tuple[str, ...] | list[str] = (),
    industries: tuple[str, ...] | list[str] = (),
    countries: tuple[str, ...] | list[str] = (),
    competitors: tuple[str, ...] | list[str] = (),
    max_queries: int = MAX_QUERIES,
) -> list[DiscoveryQuery]:
    """Expand identifiers into a bounded, de-duplicated, deterministic query set."""
    name = _clean(company_name)
    if not name:
        return []
    queries: list[DiscoveryQuery] = []
    seen: set[str] = set()

    def add(text: str, category: str) -> None:
        cleaned = _clean(text)
        if not cleaned:
            return
        key = cleaned.casefold()
        if key in seen:
            return
        seen.add(key)
        queries.append(DiscoveryQuery(text=cleaned, category=category))

    for category, templates in CATEGORY_TEMPLATES.items():
        for template in templates:
            add(template.format(name=name), category)
    for template in _REGISTRY_TEMPLATES:
        add(template.format(name=name), "company")

    for value in map(_clean, subsidiaries):
        for template in SUBSIDIARY_TEMPLATES:
            add(template.format(value=value, name=name), "company")
    for value in map(_clean, brands):
        for template in BRAND_TEMPLATES:
            add(template.format(value=value), "company")
    for value in map(_clean, products):
        for template in PRODUCT_TEMPLATES:
            add(template.format(value=value), "company")
    for value in map(_clean, former_names):
        for template in FORMER_TEMPLATES:
            add(template.format(value=value), "news")
    for value in map(_clean, leaders):
        for template in LEADER_TEMPLATES:
            add(template.format(value=value, name=name), "leadership")
    for value in map(_clean, competitors):
        for template in COMPETITOR_TEMPLATES:
            add(template.format(value=value), "competitors")
    for value in map(_clean, industries):
        for template in INDUSTRY_TEMPLATES:
            add(template.format(value=value, name=name), "company")
    for value in map(_clean, countries):
        for template in COUNTRY_TEMPLATES:
            add(template.format(value=value, name=name), "signals")

    if domain:
        bare = _clean(domain).lower().removeprefix("www.")
        if bare:
            add(bare, "company")
    return queries[: max(1, max_queries)]


def query_terms(queries: list[DiscoveryQuery], company_name: str) -> set[str]:
    """Terms used for relevance scoring, excluding generic research words."""
    generic = {
        "company", "profile", "annual", "report", "pdf", "financial", "results",
        "investor", "relations", "news", "press", "release", "industry", "market",
        "product", "portfolio", "subsidiaries", "competitors", "leadership", "strategy",
        "regulatory", "filings", "registry", "former", "interview", "comparison",
        "technology", "expansion", "operations", "business", "model", "history",
    }
    terms: set[str] = set()
    for query in queries:
        terms |= _tokens(query.text)
    terms -= generic
    terms |= _tokens(_clean(company_name))
    return {term for term in terms if len(term) >= 3}
