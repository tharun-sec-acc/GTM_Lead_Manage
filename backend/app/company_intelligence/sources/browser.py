import time
from collections.abc import Callable
from urllib.parse import urlsplit

from app.config import settings
from app.company_intelligence.sources.website import SourceError, _pinned_request, _Response, _same_site


class BrowserRenderer:
    def __init__(self, domain: str, deadline: float, can_fetch: Callable[[str], bool],
                 crawl_delay: float, cancelled: Callable[[], bool] | None):
        self.domain = domain
        self.deadline = deadline
        self.can_fetch = can_fetch
        self.crawl_delay = crawl_delay
        self.cancelled = cancelled
        self.requests = 0
        self.consumed = 0
        self.remaining = 0
        self.notes: list[str] = []
        self._playwright = None
        self._browser = None
        self._last_request = 0.0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._playwright:
                self._playwright.stop()

    def _allowed(self, request) -> bool:
        parsed = urlsplit(request.url)
        return (
            request.method == "GET"
            and request.resource_type in {"document", "script", "stylesheet", "xhr", "fetch"}
            and parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            and _same_site(parsed.hostname, self.domain)
            and self.can_fetch(request.url)
        )

    def _route(self, route, request, initial: _Response):
        if (not self._allowed(request) or time.monotonic() >= self.deadline
                or (self.cancelled and self.cancelled())):
            route.abort()
            return
        if request.resource_type == "stylesheet":
            # Text-only rendering omits visual dependencies while allowing SPA stylesheet-load gates to complete.
            route.fulfill(status=200, content_type="text/css", body="/* Styles omitted for text-only research. */")
            return
        if request.is_navigation_request() and request.url == initial.url:
            response = initial
        else:
            if self.requests >= 60 or self.remaining <= 0:
                self.notes.append("Browser resource request/byte budget reached.")
                route.abort()
                return
            self.requests += 1
            budget = min(max(1, settings.research_max_content_size), self.remaining)
            try:
                delay = self.crawl_delay - (time.monotonic() - self._last_request)
                if delay > 0:
                    time.sleep(min(delay, max(0, self.deadline - time.monotonic())))
                self._last_request = time.monotonic()
                response = _pinned_request(
                    request.url, self.domain, budget, can_fetch=self.can_fetch, deadline=self.deadline,
                )
            except SourceError as exc:
                self.consumed += budget
                self.remaining -= budget
                self.notes.append(f"Browser resource unavailable: {exc}")
                route.abort()
                return
            self.consumed += len(response.body)
            self.remaining -= len(response.body)
        headers = {key: value for key, value in response.headers.items()
                   if key not in {"content-length", "content-encoding", "transfer-encoding", "connection", "set-cookie"}}
        route.fulfill(status=response.status, headers=headers, body=response.body)

    def render(self, response: _Response, remaining_bytes: int) -> _Response:
        try:
            from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout, sync_playwright
        except ImportError as exc:
            raise SourceError("Browser research requires Playwright and its Chromium installation.") from exc
        self.consumed = 0
        self.notes = []
        self.remaining = remaining_bytes
        self._last_request = time.monotonic()
        context = None
        try:
            if not self._browser:
                self._playwright = sync_playwright().start()
                # Chromium has no direct network path; all allowed traffic is fulfilled by the pinned HTTP broker.
                self._browser = self._playwright.chromium.launch(
                    headless=True, proxy={"server": "http://127.0.0.1:9"},
                    args=["--disable-background-networking", "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
                )
            context = self._browser.new_context(
                service_workers="block", accept_downloads=False, user_agent="GTMProspectingResearch/1.0",
            )
            context.route("**/*", lambda route, request: self._route(route, request, response))
            context.route_web_socket("**/*", lambda websocket: websocket.close())
            page = context.new_page()
            timeout = max(1, int(min(settings.research_request_timeout, self.deadline - time.monotonic()) * 1000))
            page.goto(response.url, wait_until="domcontentloaded", timeout=timeout)
            try:
                page.wait_for_function(
                    "document.body && document.body.innerText.trim().length >= 200",
                    timeout=max(1, min(4000, int((self.deadline - time.monotonic()) * 1000))),
                )
            except PlaywrightTimeout:
                self.notes.append("Browser content wait expired; only available rendered text was collected.")
            if time.monotonic() >= self.deadline or (self.cancelled and self.cancelled()):
                raise SourceError("Browser collection stopped at its cancellation or duration limit.")
            html = page.content().encode("utf-8")
            if len(html) > settings.research_max_content_size:
                raise SourceError("Rendered page exceeds the configured content-size limit.")
            return _Response(page.url, 200, {"content-type": "text/html; charset=utf-8"}, html)
        except PlaywrightError as exc:
            raise SourceError("Browser rendering failed or timed out; the page may require unsupported resources.") from exc
        finally:
            if context:
                context.close()
