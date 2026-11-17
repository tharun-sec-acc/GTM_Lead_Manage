import hashlib
import http.client
import json
import ipaddress
import re
import socket
import ssl
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.config import settings


class SourceError(RuntimeError):
    pass


@dataclass
class Page:
    url: str
    title: str
    text: str
    links: list[str]
    published_at: datetime | None
    category: str
    content_hash: str
    retrieval_method: str = "http"
    external_links: list[str] = field(default_factory=list)


@dataclass
class _Response:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


class _HTMLDocument(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self.metadata: dict[str, str] = {}
        self.in_title = False
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag in {"script", "style", "noscript", "svg", "template"}:
            self.hidden_depth += 1
        if tag == "a" and attrs.get("href"):
            self.links.append(attrs["href"])
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            value = attrs.get("content", "").strip()
            if key and value:
                self.metadata[key] = value
        if tag in {"p", "div", "li", "h1", "h2", "h3", "br", "tr"}:
            self.text_parts.append(" ")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag in {"script", "style", "noscript", "svg", "template"} and self.hidden_depth:
            self.hidden_depth -= 1
        if tag in {"p", "div", "li", "h1", "h2", "h3", "tr"}:
            self.text_parts.append(" ")

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if not self.hidden_depth:
            self.text_parts.append(data)


def normalize_domain(value: str) -> str:
    raw = value.strip()
    try:
        parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
        port = parsed.port
    except ValueError as exc:
        raise SourceError("Enter a valid public company domain and standard port.") from exc
    if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
        raise SourceError("Enter a public HTTP(S) company website without credentials.")
    if port not in (None, 80, 443):
        raise SourceError("Only standard HTTP and HTTPS website ports are allowed.")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not hostname or len(hostname) > 253 or not re.fullmatch(r"[a-z0-9.-]+", hostname):
        raise SourceError("Enter a valid public company domain.")
    if any(not part or len(part) > 63 or part.startswith("-") or part.endswith("-")
           for part in hostname.split(".")):
        raise SourceError("Enter a valid public company domain.")
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal", ".test")):
        raise SourceError("Private and local website destinations are not allowed.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address and not _is_public_ip(address):
        raise SourceError("Private and reserved IP destinations are not allowed.")
    return hostname[4:] if hostname.startswith("www.") else hostname


def _is_public_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not (
        address.is_private or address.is_loopback or address.is_link_local
        or address.is_multicast or address.is_reserved or address.is_unspecified
    )


def _validated_ips(hostname: str, port: int) -> list[str]:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal:
        addresses = [str(literal)]
    else:
        try:
            records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise SourceError("Company website DNS lookup failed.") from exc
        addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not _is_public_ip(ipaddress.ip_address(item)) for item in addresses):
        raise SourceError("Company website resolves to a private, reserved, or mixed public/private address.")
    return addresses


def _same_site(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    return host == domain or host == f"www.{domain}"


def _pinned_request(url: str, allowed_domain: str | None, max_bytes: int,
                    allow_not_found: bool = False, can_fetch: Callable[[str], bool] | None = None,
                    deadline: float | None = None) -> _Response:
    max_bytes = max(1, min(100_000_000, max_bytes))
    current = url
    deadline = min(deadline or float("inf"), time.monotonic() + max(1, settings.research_request_timeout))
    for _ in range(4):
        if time.monotonic() >= deadline:
            raise SourceError("Company website request time budget reached.")
        if can_fetch and not can_fetch(current):
            raise SourceError("Company website robots policy disallows this page or redirect.")
        try:
            parsed = urlsplit(current)
            explicit_port = parsed.port
        except ValueError as exc:
            raise SourceError("Company website returned an invalid URL or port.") from exc
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise SourceError("Only public HTTP(S) pages can be retrieved.")
        if parsed.username or parsed.password or parsed.fragment:
            if parsed.username or parsed.password:
                raise SourceError("Authenticated website URLs are not supported.")
        host = parsed.hostname.lower().rstrip(".")
        if allowed_domain is not None and not _same_site(host, allowed_domain):
            raise SourceError("Redirects and links must remain on the confirmed company website.")
        port = explicit_port or (443 if parsed.scheme == "https" else 80)
        if port != (443 if parsed.scheme == "https" else 80):
            raise SourceError("Non-standard website ports are not allowed.")
        addresses = _validated_ips(host, port)
        path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if parsed.query:
            path += "?" + quote(parsed.query, safe="=&;%:@!$'()*+,-._~/?")
        last_error = None
        response = None
        for address in addresses[:1]:
            sock = None
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SourceError("Company website request time budget reached.")
                sock = socket.create_connection((address, port), timeout=remaining)
                if parsed.scheme == "https":
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
                request = (
                    f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: GTMProspectingResearch/1.0\r\n"
                    f"Accept: text/html,application/pdf,application/xhtml+xml;q=0.9,*/*;q=0.1\r\n"
                    f"Accept-Encoding: identity\r\nConnection: close\r\n\r\n"
                ).encode("ascii")
                sock.sendall(request)
                raw = http.client.HTTPResponse(sock)
                raw.begin()
                headers = {key.lower(): value for key, value in raw.getheaders()}
                if raw.status in {301, 302, 303, 307, 308}:
                    location = headers.get("location")
                    raw.close()
                    if not location:
                        raise SourceError("Company website returned a redirect without a destination.")
                    current = urljoin(current, location)
                    response = None
                    break
                if raw.status == 404 and allow_not_found:
                    if headers.get("content-encoding", "identity").lower() not in ("", "identity"):
                        raise SourceError("Website returned a compressed robots response.")
                    body = _read_body(raw, sock, max_bytes, deadline)
                    if len(body) > max_bytes:
                        raise SourceError("Website robots policy exceeds the configured byte limit.")
                    raw.close()
                    response = _Response(current, raw.status, headers, body)
                    break
                if raw.status < 200 or raw.status >= 300:
                    raise SourceError(f"Company website returned HTTP {raw.status}.")
                if headers.get("content-encoding", "identity").lower() not in ("", "identity"):
                    raise SourceError("Compressed website responses are not accepted.")
                content_length = headers.get("content-length")
                if content_length and int(content_length) > max_bytes:
                    raise SourceError("Company website page exceeds the configured byte limit.")
                body = _read_body(raw, sock, max_bytes, deadline)
                if len(body) > max_bytes:
                    raise SourceError("Company website page exceeds the configured byte limit.")
                raw.close()
                response = _Response(current, raw.status, headers, body)
                break
            except SourceError:
                raise
            except (OSError, ssl.SSLError, http.client.HTTPException, ValueError) as exc:
                last_error = exc
            finally:
                if sock:
                    try:
                        sock.close()
                    except OSError:
                        pass
        if response:
            return response
        if last_error:
            raise SourceError("Could not retrieve the public company website.") from last_error
    raise SourceError("Company website exceeded the safe redirect limit.")


def _read_body(response: http.client.HTTPResponse, sock: socket.socket, max_bytes: int, deadline: float) -> bytes:
    parts = []
    length = 0
    while length <= max_bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceError("Company website request time budget reached.")
        sock.settimeout(remaining)
        chunk = response.read1(min(65536, max_bytes + 1 - length))
        if not chunk:
            break
        parts.append(chunk)
        length += len(chunk)
    return b"".join(parts)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def _path_category(path: str) -> str:
    lowered = path.lower()
    if any(item in lowered for item in ("news", "press", "media", "announcement", "blog")):
        return "news"
    if any(item in lowered for item in ("investor", "financial", "annual-report", "filing")):
        return "financial"
    if any(item in lowered for item in ("funding", "investment", "acquisition", "merger")):
        return "funding"
    if any(item in lowered for item in ("leadership", "management", "team", "director")):
        return "leadership"
    if any(item in lowered for item in ("career", "hiring", "expansion", "technology", "sustainability")):
        return "signals"
    return "company"


def _text_from_pdf(content: bytes) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SourceError("PDF extraction is unavailable until the optional pypdf dependency is installed.") from exc
    from io import BytesIO

    try:
        reader = PdfReader(BytesIO(content), strict=True)
        if len(reader.pages) > 100:
            raise SourceError("PDF exceeds the configured page extraction limit.")
        return [(index + 1, re.sub(r"\s+", " ", page.extract_text() or "").strip())
                for index, page in enumerate(reader.pages)]
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError("Company website returned an unreadable PDF.") from exc


def _make_page(response: _Response, base_domain: str) -> Page | None:
    media_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type == "application/pdf" or response.url.lower().endswith(".pdf"):
        pages = _text_from_pdf(response.body)
        text = "\n".join(f"[Page {number}] {page_text}" for number, page_text in pages if page_text)
        if not text:
            return None
        title = urlsplit(response.url).path.rsplit("/", 1)[-1] or "Company PDF"
        category = _path_category(urlsplit(response.url).path)
        return Page(response.url, title, text[:max(1, settings.research_max_content_size)], [], None,
                    category, hashlib.sha256(response.body).hexdigest(), "http_pdf")
    if media_type not in {"text/html", "application/xhtml+xml"}:
        raise SourceError("Company website returned a non-HTML, non-PDF response.")
    charset = response.headers.get("content-type", "")
    match = re.search(r"charset=([\w-]+)", charset, flags=re.IGNORECASE)
    try:
        html = response.body.decode(match.group(1) if match else "utf-8", errors="replace")
    except LookupError:
        html = response.body.decode("utf-8", errors="replace")
    parser = _HTMLDocument()
    parser.feed(html)
    parser.close()
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    if not text:
        return None
    title = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip() or parser.metadata.get("og:title", "")
    if any(marker in title.casefold() for marker in ("access denied", "just a moment", "verify you are human", "captcha")):
        raise SourceError("Website returned an access-control or anti-bot challenge; it will not be bypassed.")
    published = _parse_date(
        parser.metadata.get("article:published_time") or parser.metadata.get("datepublished")
        or parser.metadata.get("date")
    )
    links = []
    external = []
    for link in parser.links[:2000]:
        resolved = urljoin(response.url, link)
        parsed = urlsplit(resolved)
        if parsed.scheme in {"http", "https"} and parsed.hostname:
            clean = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))
            if _same_site(parsed.hostname, base_domain):
                links.append(clean)
            else:
                external.append(clean)
    return Page(response.url, title[:1000], text[:max(1, settings.research_max_content_size)],
                list(dict.fromkeys(links)), published, _path_category(urlsplit(response.url).path),
                hashlib.sha256(response.body).hexdigest(), "http",
                list(dict.fromkeys(external))[:500])


def _json_page(response: _Response) -> Page | None:
    """Render a public JSON registry/API record as retrievable text evidence."""
    try:
        data = json.loads(response.body.decode("utf-8", errors="replace"))
    except ValueError:
        return None
    lines: list[str] = []

    def walk(value, prefix: str = "") -> None:
        if len(lines) > 4000:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{prefix}{key}.")
        elif isinstance(value, list):
            for index, item in enumerate(value[:20]):
                walk(item, f"{prefix}{index}.")
        elif value is not None and not isinstance(value, (dict, list)):
            lines.append(f"{prefix.rstrip('.') or 'value'}: {value}")

    walk(data)
    text = "\n".join(lines).strip()
    if not text:
        return None
    title = "Public registry record"
    try:
        candidate = data["data"]
        candidate = candidate[0] if isinstance(candidate, list) and candidate else candidate
        title = str(candidate["attributes"]["entity"]["legalName"]["name"])[:1000]
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return Page(response.url, title, text[:max(1, settings.research_max_content_size)], [], None,
                "company", hashlib.sha256(response.body).hexdigest(), "http_json")


def _page_priority(url: str) -> tuple[int, str]:
    path = urlsplit(url).path.lower()
    priorities = (
        ("about", 0), ("company", 1), ("product", 2), ("service", 3), ("leadership", 4),
        ("team", 4), ("investor", 5), ("financial", 5), ("annual-report", 5), ("news", 6),
        ("press", 6), ("career", 7), ("location", 8), ("contact", 9),
    )
    return (next((priority for token, priority in priorities if token in path), 10), url)


def gather_official_pages(domain: str, max_pages: int, max_depth: int,
                          max_total_bytes: int, cancelled: Callable[[], bool] | None = None) -> tuple[list[Page], list[str], int]:
    from app.company_intelligence.sources.browser import BrowserRenderer

    scheme = "https"
    start = f"{scheme}://{domain}/"
    robots_url = f"{scheme}://{domain}/robots.txt"
    limitations: list[str] = []
    deadline = time.monotonic() + max(1, min(600, settings.research_max_duration_seconds))
    parser = RobotFileParser(robots_url)
    try:
        robots = _pinned_request(
            robots_url, domain, max(1, min(settings.research_max_content_size, 65536)),
            allow_not_found=True,
            deadline=deadline,
        )
        parser.parse([] if robots.status == 404 else robots.body.decode("utf-8", errors="replace").splitlines())
    except SourceError as exc:
        parser.parse(["User-agent: *", "Disallow: /"])
        limitations.append(f"Website crawling stopped because robots.txt could not be checked: {exc}")
        return [], limitations, min(settings.research_max_content_size, 65536, max_total_bytes)
    if not parser.can_fetch("GTMProspectingResearch", start):
        return [], ["Company website robots policy disallows automated research."], 0
    crawl_delay = parser.crawl_delay("GTMProspectingResearch") or 0
    rate = parser.request_rate("GTMProspectingResearch")
    if rate and rate.requests:
        crawl_delay = max(crawl_delay, rate.seconds / rate.requests)
    if crawl_delay > 10:
        return [], ["Website robots crawl delay exceeds this bounded research worker's supported interval."], len(robots.body)

    max_bytes_per_page = max(1, min(settings.research_max_content_size, max_total_bytes))
    pages: list[Page] = []
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start, 0)]
    total_bytes = len(robots.body)
    with BrowserRenderer(domain, deadline, lambda target: parser.can_fetch("GTMProspectingResearch", target),
                         crawl_delay, cancelled) as browser:
        while queue and len(pages) < max_pages:
            if (cancelled and cancelled()) or time.monotonic() >= deadline or len(visited) >= max_pages * 2:
                limitations.append("Source collection stopped at its cancellation, duration or request-count limit.")
                break
            url, depth = queue.pop(0)
            parsed = urlsplit(url)
            clean_url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))
            if clean_url in visited or not parser.can_fetch("GTMProspectingResearch", clean_url):
                continue
            visited.add(clean_url)
            if max_total_bytes - total_bytes <= 0:
                limitations.append("Cumulative company source-byte budget reached.")
                break
            request_budget = min(max_bytes_per_page, max_total_bytes - total_bytes)
            try:
                if crawl_delay:
                    time.sleep(min(crawl_delay, max(0, deadline - time.monotonic())))
                response = _pinned_request(clean_url, domain, request_budget,
                                           can_fetch=lambda target: parser.can_fetch("GTMProspectingResearch", target),
                                           deadline=deadline)
            except SourceError as exc:
                total_bytes += request_budget
                limitations.append(f"{clean_url}: {exc}")
                continue
            total_bytes += len(response.body)
            try:
                page = _make_page(response, domain)
                if (b"<script" in response.body.lower() and (not page or len(page.text) < 200)
                        and "html" in response.headers.get("content-type", "")):
                    if settings.research_browser_enabled:
                        try:
                            rendered = browser.render(response, max(0, max_total_bytes - total_bytes))
                        finally:
                            total_bytes += browser.consumed
                            limitations.extend(browser.notes[:4])
                        page = _make_page(rendered, domain)
                        if page:
                            page.retrieval_method = "playwright"
                            if len(page.text) < 200:
                                limitations.append(f"{clean_url}: Browser returned little usable text; coverage is limited.")
                    else:
                        limitations.append(f"{clean_url}: JavaScript content requires RESEARCH_BROWSER_ENABLED.")
            except SourceError as exc:
                limitations.append(f"{clean_url}: {exc}")
                continue
            if not page:
                continue
            pages.append(page)
            if depth < max_depth:
                children = sorted((link for link in page.links if link not in visited), key=_page_priority)
                queue.extend((link, depth + 1) for link in children[:max_pages * 2])
                queue = sorted(dict.fromkeys(queue), key=lambda item: _page_priority(item[0]))[:max_pages * 2]
    if queue and len(pages) >= max_pages:
        limitations.append("Configured maximum page count reached.")
    return pages, limitations, total_bytes


_ROBOTS_CACHE: dict[str, tuple[RobotFileParser, list[str]]] = {}


def clear_robots_cache() -> None:
    _ROBOTS_CACHE.clear()


def robots_for(host: str, deadline: float | None = None) -> tuple[RobotFileParser, list[str], int]:
    """Fetch and cache robots.txt for a public host. Fail closed on retrieval errors."""
    host = host.lower().rstrip(".")
    if host in _ROBOTS_CACHE:
        parser, notes = _ROBOTS_CACHE[host]
        return parser, list(notes), 0
    parser = RobotFileParser(f"https://{host}/robots.txt")
    notes: list[str] = []
    consumed = 0
    try:
        response = _pinned_request(f"https://{host}/robots.txt", host, 65536,
                                   allow_not_found=True, deadline=deadline)
        consumed = len(response.body)
        parser.parse([] if response.status == 404
                     else response.body.decode("utf-8", errors="replace").splitlines())
    except SourceError as exc:
        parser.parse(["User-agent: *", "Disallow: /"])
        notes.append(f"{host}: robots policy could not be checked ({exc}); domain skipped.")
    _ROBOTS_CACHE[host] = (parser, list(notes))
    return parser, notes, consumed


def crawl_delay_for(parser: RobotFileParser) -> float:
    delay = parser.crawl_delay("GTMProspectingResearch") or 0
    rate = parser.request_rate("GTMProspectingResearch")
    if rate and rate.requests:
        delay = max(delay, rate.seconds / rate.requests)
    return min(float(delay), 5.0)


def fetch_public_text(url: str, max_bytes: int, deadline: float | None = None,
                      can_fetch: Callable[[str], bool] | None = None) -> tuple[str, str]:
    """Fetch a public text/XML/JSON resource. Returns (decoded body, content type)."""
    response = _pinned_request(url, None, max_bytes, can_fetch=can_fetch, deadline=deadline)
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    text_like = (content_type.startswith("text/") or content_type.endswith(("+json", "+xml"))
                 or content_type in {
                     "application/json", "application/xml", "application/rss+xml",
                     "application/atom+xml", "application/xhtml+xml",
                 })
    if content_type and not text_like:
        raise SourceError("The discovered resource was not a text, XML or JSON document.")
    return response.body.decode("utf-8", errors="replace"), content_type


def fetch_public_page(url: str, max_bytes: int, deadline: float | None = None,
                      can_fetch: Callable[[str], bool] | None = None) -> Page:
    """Fetch a public page or PDF, validating SSRF and redirect rules at every hop."""
    response = _pinned_request(url, None, max_bytes, can_fetch=can_fetch, deadline=deadline)
    host = (urlsplit(response.url).hostname or "").lower().rstrip(".")
    page = _make_page(response, host)
    if not page:
        raise SourceError("The page contained no usable text.")
    return page


def fetch_public_page_adaptive(url: str, max_bytes: int, deadline: float | None = None,
                               can_fetch: Callable[[str], bool] | None = None,
                               cancelled: Callable[[], bool] | None = None) -> tuple[Page, list[str]]:
    """Static retrieval first, then an opt-in text-only browser fallback for JS shells."""
    response = _pinned_request(url, None, max_bytes, can_fetch=can_fetch, deadline=deadline)
    host = (urlsplit(response.url).hostname or "").lower().rstrip(".")
    content_type = response.headers.get("content-type", "").lower()
    notes: list[str] = []
    page = _json_page(response) if "json" in content_type else _make_page(response, host)
    if (settings.research_browser_enabled and "html" in content_type
            and (page is None or len(page.text) < 200)
            and (cancelled is None or not cancelled())):
        from app.company_intelligence.sources.browser import BrowserRenderer

        with BrowserRenderer(host, deadline or time.monotonic() + max(1, settings.research_request_timeout),
                             can_fetch or (lambda _target: True), 0, cancelled) as browser:
            try:
                rendered = browser.render(response, max_bytes)
                rendered_page = _make_page(rendered, host)
                if rendered_page:
                    rendered_page.retrieval_method = "playwright"
                    page = rendered_page
            finally:
                notes.extend(browser.notes[:4])
    if not page:
        raise SourceError("The page contained no usable text after static and browser retrieval.")
    return page, notes
