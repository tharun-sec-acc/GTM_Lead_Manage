"""Source policy: URL normalisation, classification, blocking and relevance scoring.

A discovered URL is a lead. These rules decide whether it is worth fetching, not whether it
contains a fact.
"""

import ipaddress
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "igshid", "ref_src",
}

BLOCKED_EXTENSIONS = {
    ".exe", ".msi", ".dmg", ".zip", ".rar", ".7z", ".tar", ".gz", ".iso",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".mp4", ".mp3",
    ".avi", ".mov", ".css", ".js", ".woff", ".woff2", ".ttf", ".xml",
}

BLOCKED_PATH_TOKENS = (
    "/login", "/signin", "/sign-in", "/signup", "/register", "/cart", "/checkout",
    "/account", "/wp-admin", "/cookie", "/privacy", "/terms", "/unsubscribe",
)

SOCIAL_DOMAINS = (
    "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
    "tiktok.com", "youtube.com", "pinterest.com", "reddit.com", "threads.net",
)

# domain suffix -> source type
DOMAIN_TYPES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("sec.gov", "gov.uk", "europa.eu", "companieshouse.gov.uk", "asx.com.au",
      "sedar.com", "companieshouse", "mca.gov.in", "sebi.gov.in", "gleif.org"), "registry"),
    (("reuters.com", "bloomberg.com", "ft.com", "wsj.com", "apnews.com", "cnbc.com",
      "prnewswire.com", "businesswire.com", "globenewswire.com", "accesswire.com",
      "marketwatch.com", "yahoo.com"), "news"),
    (("annualreports.com", "annualreports", "secfilings.com", "last10k.com"), "financial"),
    (("wikipedia.org", "wikidata.org", "crunchbase.com", "opencorporates.com",
      "bloomberg.com/profile", "zoominfo.com"), "directory"),
    (("arxiv.org", "zenodo.org", "ssrn.com", "researchgate.net", "doaj.org"), "document"),
    (("industryweek.com", "automotivenews.com", "autonews.com", "manufacturing.net",
      "supplychaindive.com", "procurement", "just-auto.com"), "industry"),
)

PATH_CATEGORY_TOKENS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("press-release", "press_release", "press-release", "/press", "/news", "/media",
      "/announcement", "/blog"), "news"),
    (("annual-report", "annual_report", "investor", "/financial", "/filing", "/results",
      "/reports"), "financial"),
    (("leadership", "/management", "/team", "/director", "/board"), "leadership"),
    (("acquisition", "merger", "funding", "investment"), "funding"),
    (("career", "hiring", "expansion", "sustainability", "technology"), "signals"),
)

CATEGORY_WEIGHTS = {
    "registry": 0.88,
    "financial": 0.86,
    "document": 0.8,
    "news": 0.78,
    "directory": 0.74,
    "industry": 0.72,
    "official": 0.5,
    "other": 0.34,
    "social": 0.0,
}

_TYPE_TO_RESEARCH_CATEGORY = {
    "official": "company",
    "registry": "company",
    "directory": "company",
    "document": "company",
    "financial": "financial",
    "news": "news",
    "industry": "competitors",
    "other": "company",
    "social": "news",
}

RELIABILITY = {
    "official": "official",
    "registry": "registry",
    "financial": "primary_document",
    "news": "news",
    "directory": "directory",
    "document": "document",
    "industry": "industry",
    "other": "unclassified",
    "social": "social",
}


def _host_is_private(host: str) -> bool:
    host = host.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal", "metadata"}:
        return True
    if host.endswith((".localhost", ".local", ".internal", ".test", ".invalid")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    return not address.is_global or address.is_private or address.is_loopback \
        or address.is_link_local or address.is_reserved or address.is_multicast


def normalize_candidate_url(url: str) -> str | None:
    """Normalise a candidate URL or return None when it is unusable."""
    if not isinstance(url, str):
        return None
    raw = url.strip()
    if not raw or raw.lower().startswith(("javascript:", "mailto:", "tel:", "data:")):
        return None
    try:
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    host = parsed.hostname.lower().rstrip(".")
    if _host_is_private(host):
        return None
    if port not in (None, 80, 443):
        return None
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if key.lower() not in TRACKING_PARAMS]
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    return urlunsplit((parsed.scheme, netloc, path, urlencode(sorted(query)), ""))


def is_blocked_url(url: str) -> tuple[bool, str]:
    """Return (blocked, reason). Policy is deliberately conservative."""
    normalized = normalize_candidate_url(url)
    if not normalized:
        return True, "unusable or non-public URL"
    parsed = urlsplit(normalized)
    host = (parsed.hostname or "").lower()
    path = parsed.path.lower()
    if any(host == domain or host.endswith(f".{domain}") for domain in SOCIAL_DOMAINS):
        return True, "social network"
    if any(path.endswith(extension) for extension in BLOCKED_EXTENSIONS):
        return True, "unsupported content type"
    if any(token in path for token in BLOCKED_PATH_TOKENS):
        return True, "access or account path"
    if path.count("/") > 6:
        return True, "path too deep"
    if ":" in host and not host.endswith("]"):
        return True, "unexpected host format"
    return False, ""


def _matches_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith(f".{domain}")


def source_type_for(url: str, official_domain: str | None) -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if official_domain and _matches_domain(host, official_domain):
        return "official"
    for domains, source_type in DOMAIN_TYPES:
        if any(_matches_domain(host, domain) for domain in domains):
            return source_type
    return "other"


def research_category_for(source_type: str, url: str) -> str:
    path = (urlsplit(url).path or "").lower()
    for tokens, category in PATH_CATEGORY_TOKENS:
        if any(token in path for token in tokens):
            return category
    return _TYPE_TO_RESEARCH_CATEGORY.get(source_type, "company")


def reliability_for(source_type: str) -> str:
    return RELIABILITY.get(source_type, "unclassified")


def relevance_score(url: str, title: str, terms: set[str], source_type: str,
                    official_domain: str | None) -> tuple[float, list[str]]:
    """Score a candidate from 0 to 1 using type weight and identifier matches."""
    score = CATEGORY_WEIGHTS.get(source_type, 0.2)
    if source_type != "official" and official_domain:
        score += 0.10  # cross-domain discovery is the objective
    haystack = re.sub(r"[^a-z0-9]+", " ", f"{title} {url}".casefold())
    hits = sorted(term for term in terms if term in haystack)
    score += min(0.48, 0.12 * len(hits))
    path = urlsplit(url).path.lower()
    if any(token in path for token in ("/tag/", "/author/", "/page/", "/search")):
        score -= 0.15
    if path.count("/") > 4:
        score -= 0.1
    return max(0.0, min(1.0, round(score, 4))), hits[:12]
