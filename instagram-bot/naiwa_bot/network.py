import ipaddress
from pathlib import Path
import socket
from urllib.parse import urljoin, urlparse

import httpx


class RemoteError(RuntimeError):
    pass


def checked_json(response):
    if response.is_error:
        # Do not copy response bodies, URLs, or request objects into public logs.
        detail = ""
        try:
            remote = response.json().get("error", {})
            if isinstance(remote, dict):
                values = [f"{key}={remote[key]}" for key in ("code", "error_subcode") if type(remote.get(key)) is int]
                if values:
                    detail = " (" + ", ".join(values) + ")"
        except (ValueError, AttributeError):
            pass
        raise RemoteError(f"Remote API returned HTTP {response.status_code}{detail}")
    try:
        return response.json()
    except ValueError:
        raise RemoteError("Remote API returned invalid JSON") from None


def validate_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Only public HTTPS URLs without credentials are supported")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ValueError("Private/local network URLs are forbidden")


def download(client, url, target: Path, max_bytes=80_000_000):
    for _ in range(5):
        validate_public_url(url)
        with client.stream("GET", url, follow_redirects=False, timeout=90) as response:
            if response.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers["location"])
                continue
            if response.status_code != 200:
                raise RemoteError(f"Media download returned HTTP {response.status_code}")
            total = 0
            temporary = target.with_suffix(".part")
            try:
                with temporary.open("wb") as output:
                    for chunk in response.iter_bytes(65536):
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("Media download exceeds size limit")
                        output.write(chunk)
                if not total:
                    raise ValueError("Empty media file")
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
            return
    raise ValueError("Too many media redirects")
