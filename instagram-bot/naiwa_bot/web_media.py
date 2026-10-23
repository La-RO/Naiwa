"""Find a public video URL without downloading a web player or running its scripts."""

from html.parser import HTMLParser
import json
from urllib.parse import urljoin, urldefrag, urlparse

import httpx

from .network import RemoteError, validate_public_url


MAX_HTML_BYTES = 1_000_000
MAX_REDIRECTS = 5
MAX_CANDIDATES = 10
REDIRECT_CODES = (301, 302, 303, 307, 308)


class _VideoParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.candidates = []
        self.preferred = set()
        self._json_script = None

    def add_candidate(self, value, preferred=False):
        if isinstance(value, str) and value.strip() and len(self.candidates) < MAX_CANDIDATES:
            value = value.strip()
            if value not in self.candidates:
                self.candidates.append(value)
            if preferred:
                self.preferred.add(value)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("video", "source"):
            kind = (attrs.get("type") or "").lower().split(";", 1)[0].strip()
            if kind in ("", "video/mp4", "application/mp4"):
                self.add_candidate(attrs.get("src"), preferred=kind in ("video/mp4", "application/mp4"))
        elif tag == "meta":
            name = (attrs.get("property") or attrs.get("name") or "").lower()
            if name in ("og:video", "og:video:url", "og:video:secure_url"):
                self.add_candidate(attrs.get("content"))
        elif tag == "script":
            kind = (attrs.get("type") or "").lower().split(";", 1)[0].strip()
            self._json_script = [] if kind == "application/ld+json" else None

    def handle_data(self, data):
        if self._json_script is not None:
            self._json_script.append(data)

    def handle_endtag(self, tag):
        if tag != "script" or self._json_script is None:
            return
        raw = "".join(self._json_script)
        self._json_script = None
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            return
        pending = [data]
        # Bound traversal even for large, deeply nested structured metadata.
        for _ in range(1000):
            if not pending or len(self.candidates) >= MAX_CANDIDATES:
                break
            item = pending.pop()
            if isinstance(item, list):
                pending.extend(reversed(item))
            elif isinstance(item, dict):
                types = item.get("@type", [])
                if isinstance(types, str):
                    types = [types]
                if isinstance(types, list) and any(
                    isinstance(value, str) and value.rstrip("/").rsplit("/", 1)[-1] == "VideoObject"
                    for value in types
                ):
                    self.add_candidate(item.get("contentUrl"))
                pending.extend(reversed(list(item.values())))


def _public_candidate(source_url, candidate):
    try:
        candidate = urldefrag(urljoin(source_url, candidate))[0]
        validate_public_url(candidate)
    except (ValueError, OSError):
        return None
    return candidate


def find_video(client, source_url) -> str | None:
    """Resolve direct MP4 media or static HTML video metadata on a public page.

    Candidate URLs are validated but not fetched here. The caller must download
    and validate the selected media before it enters the publication queue.
    """
    url = source_url
    for redirects in range(MAX_REDIRECTS + 1):
        try:
            validate_public_url(url)
        except OSError:
            raise RemoteError("Public media source could not be resolved") from None
        request = client.build_request("GET", url, timeout=30)
        # Public discovery must not forward credentials from an API client.
        request.headers.pop("authorization", None)
        request.headers.pop("cookie", None)
        try:
            response = client.send(request, auth=None, stream=True, follow_redirects=False)
            try:
                if response.status_code in REDIRECT_CODES:
                    location = response.headers.get("location")
                    if not location:
                        raise RemoteError("Public media source returned a redirect without a location")
                    if redirects == MAX_REDIRECTS:
                        raise ValueError("Too many public media source redirects")
                    url = urljoin(url, location)
                    continue
                if response.status_code != 200:
                    raise RemoteError(f"Public media source returned HTTP {response.status_code}")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if (content_type in ("video/mp4", "application/mp4")
                        or (content_type in ("", "application/octet-stream") and urlparse(url).path.lower().endswith(".mp4"))):
                    return url
                try:
                    declared_size = int(response.headers.get("content-length", "0"))
                except ValueError:
                    declared_size = 0
                if declared_size > MAX_HTML_BYTES:
                    raise ValueError("Public media source HTML exceeds size limit")
                content = bytearray()
                for chunk in response.iter_bytes(65536):
                    if len(content) + len(chunk) > MAX_HTML_BYTES:
                        raise ValueError("Public media source HTML exceeds size limit")
                    content.extend(chunk)
                try:
                    html = content.decode(response.encoding or "utf-8", errors="replace")
                except LookupError:
                    html = content.decode("utf-8", errors="replace")
            finally:
                response.close()
        except httpx.HTTPError:
            raise RemoteError("Public media source could not be fetched") from None
        parser = _VideoParser()
        parser.feed(html)
        parser.close()
        def priority(value):
            try:
                is_mp4 = urlparse(value).path.lower().endswith(".mp4")
            except ValueError:
                is_mp4 = False
            return value not in parser.preferred, not is_mp4
        candidates = sorted(parser.candidates, key=priority)
        for candidate in candidates:
            result = _public_candidate(url, candidate)
            if result:
                return result
        return None
    return None
