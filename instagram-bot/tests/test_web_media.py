import socket

import httpx
import pytest

from naiwa_bot.network import RemoteError
from naiwa_bot.web_media import find_video, MAX_HTML_BYTES


@pytest.fixture(autouse=True)
def public_dns(monkeypatch):
    def resolve(host, *_args, **_kwargs):
        address = "127.0.0.1" if host in ("private.test", "127.0.0.1") else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]
    monkeypatch.setattr("naiwa_bot.network.socket.getaddrinfo", resolve)


def client_for(handler, **kwargs):
    return httpx.Client(transport=httpx.MockTransport(handler), **kwargs)


def test_direct_media_response_is_not_downloaded():
    class UnreadableMedia(httpx.SyncByteStream):
        def __iter__(self):
            raise AssertionError("Media must be downloaded by the later validation stage")

    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "video/mp4"}, stream=UnreadableMedia())
    with client_for(handler) as client:
        assert find_video(client, "https://public.test/clip.mp4") == "https://public.test/clip.mp4"
    assert len(requests) == 1


def test_octet_stream_mp4_is_a_direct_candidate():
    with client_for(lambda request: httpx.Response(200, headers={"content-type": "application/octet-stream"},
                                                  content=b"not-downloaded-yet")) as client:
        assert find_video(client, "https://public.test/clip.mp4") == "https://public.test/clip.mp4"


def test_mp4_source_is_preferred_over_webm_or_player_page():
    html = ('<meta property="og:video" content="/player.html">'
            '<video><source src="/clip.webm" type="video/webm">'
            '<source src="/playback?id=1" type="video/mp4"></video>')
    with client_for(lambda request: httpx.Response(200, text=html)) as client:
        assert find_video(client, "https://public.test/post") == "https://public.test/playback?id=1"


def test_public_download_does_not_forward_default_credentials(tmp_path):
    from naiwa_bot.network import download
    requests = []
    def handler(request):
        requests.append(request)
        assert "authorization" not in request.headers and "cookie" not in request.headers
        return httpx.Response(200, content=b"video-data")
    with client_for(handler, auth=("user", "secret"), headers={"Cookie": "session=secret"}) as client:
        target = tmp_path / "clip.mp4"
        download(client, "https://public.test/clip.mp4", target)
    assert len(requests) == 1 and target.read_bytes() == b"video-data"


@pytest.mark.parametrize("html, expected", [
    ('<video src="../clips/frog.mp4"></video>', "https://public.test/clips/frog.mp4"),
    ('<video><source src="/frog.mp4?x=1&amp;y=2" type="video/mp4"></video>',
     "https://public.test/frog.mp4?x=1&y=2"),
    ('<meta property="og:video:secure_url" content="https://cdn.test/frog.mp4">',
     "https://cdn.test/frog.mp4"),
    ('<script type="application/ld+json">{"@graph":[{"@type":"VideoObject",'
     '"contentUrl":"/frog.mp4"}]}</script>', "https://public.test/frog.mp4"),
])
def test_static_html_media_metadata(html, expected):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)
    with client_for(handler) as client:
        assert find_video(client, "https://public.test/pages/frog") == expected
    assert len(requests) == 1  # Candidate media is checked by the later download stage.


def test_redirects_are_resolved_and_checked():
    requests = []
    def handler(request):
        requests.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/gallery/frog"})
        return httpx.Response(200, text='<source src="frog.mp4">')
    with client_for(handler) as client:
        assert find_video(client, "https://public.test/start") == "https://public.test/gallery/frog.mp4"
    assert len(requests) == 2


@pytest.mark.parametrize("target", ["https://private.test/frog", "http://public.test/frog",
                                   "https://user:secret@public.test/frog"])
def test_unsafe_redirect_is_never_requested(target):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": target})
    with client_for(handler) as client, pytest.raises(ValueError) as error:
        find_video(client, "https://public.test/start")
    assert len(requests) == 1
    assert "secret" not in str(error.value)


def test_redirect_limit():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"location": "/next"})
    with client_for(handler) as client, pytest.raises(ValueError, match="Too many"):
        find_video(client, "https://public.test/start")
    assert len(requests) == 6  # The initial request plus five redirects.


def test_unsafe_candidates_are_skipped_without_fetching():
    html = """<video src="blob:foo"></video><source src="data:video/mp4;base64,a">
        <source src="http://public.test/a.mp4"><source src="https://private.test/a.mp4">
        <source src="https://user:secret@public.test/a.mp4"><source src="https://[malformed/a.mp4">
        <source src="/safe.mp4">"""
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, text=html)
    with client_for(handler) as client:
        assert find_video(client, "https://public.test/frog") == "https://public.test/safe.mp4"
    assert len(requests) == 1


def test_only_first_ten_candidates_are_considered():
    html = "".join(f'<source src="http://public.test/{n}.mp4">' for n in range(10))
    html += '<source src="https://public.test/too-late.mp4">'
    with client_for(lambda _: httpx.Response(200, text=html)) as client:
        assert find_video(client, "https://public.test/frog") is None


@pytest.mark.parametrize("declared", [False, True])
def test_oversized_html_is_rejected(declared):
    headers = {"content-length": str(MAX_HTML_BYTES + 1)} if declared else {}
    content = b"x" * (MAX_HTML_BYTES + 1)
    with client_for(lambda _: httpx.Response(200, headers=headers, stream=httpx.ByteStream(content))) as client:
        with pytest.raises(ValueError, match="size limit"):
            find_video(client, "https://public.test/frog")


def test_no_static_video_returns_none_even_with_invalid_json():
    html = '<p>No clip.</p><script type="application/ld+json">invalid</script>'
    with client_for(lambda _: httpx.Response(200, text=html)) as client:
        assert find_video(client, "https://public.test/frog") is None


def test_missing_source_has_sanitized_error():
    with client_for(lambda _: httpx.Response(404, text="private error detail")) as client:
        with pytest.raises(RemoteError, match="HTTP 404") as error:
            find_video(client, "https://public.test/missing")
    assert "private error detail" not in str(error.value)


def test_public_fetch_omits_client_auth_and_cookies():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, text='<source src="/frog.mp4">')
    with client_for(handler, auth=("user", "secret"), cookies={"session": "secret"},
                    headers={"Authorization": "Bearer secret", "Cookie": "other=secret"}) as client:
        assert find_video(client, "https://public.test/frog") == "https://public.test/frog.mp4"
    assert "authorization" not in requests[0].headers
    assert "cookie" not in requests[0].headers


def test_connection_failure_does_not_leak_request_url():
    def handler(request):
        raise httpx.ConnectError("failed on secret signed URL", request=request)
    with client_for(handler) as client, pytest.raises(RemoteError) as error:
        find_video(client, "https://public.test/frog?token=secret")
    assert "secret" not in str(error.value)
