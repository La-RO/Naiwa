import copy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import socket
import subprocess

import httpx
import imageio_ffmpeg
import pytest

from naiwa_bot import auto_video, engine
from naiwa_bot.catalogue import eligible, publishable
from naiwa_bot.config import Config
from naiwa_bot.network import RemoteError
from naiwa_bot.state import Store


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 23, 8, 30, tzinfo=timezone.utc)
DAY = "2026-10-23"
SLOT = "story:" + DAY


class MemoryStore(Store):
    def __init__(self, path):
        super().__init__(path)
        self.snapshots = []

    def save(self):
        super().save()
        self.snapshots.append(copy.deepcopy(self.data))

    def public_url(self, relative):
        return "https://raw.public.test/" + relative


@pytest.fixture
def store(tmp_path):
    result = MemoryStore(tmp_path / "state")
    result.data["paused"] = False
    return result


@pytest.fixture
def cfg():
    result = Config.load(ROOT)
    result.discovery.update(enabled=True, auto_publish=True, only_when_story_empty=True,
                            queries=["奶蛙 视频 mp4"], max_auto_videos_per_day=1,
                            max_candidate_checks_per_day=6, keywords=["奶蛙", "naiwa"],
                            operator_policy="Operator requested automatic publication; reuse rights unverified.")
    result.ai["enabled"] = False
    return result


@pytest.fixture(autouse=True)
def fake_public_network(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-search-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("naiwa_bot.network.socket.getaddrinfo", lambda *_args, **_kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))])


@pytest.fixture(scope="module")
def valid_mp4(tmp_path_factory):
    path = tmp_path_factory.mktemp("valid-web-mp4") / "frog.mp4"
    result = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=yellow:s=160x160:r=10:d=3.2", "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path),
    ], capture_output=True, timeout=30)
    assert result.returncode == 0, "Local test MP4 generation failed"
    return path.read_bytes()


def video(store, identity="stock", digest="a" * 64, **updates):
    asset = {"id": identity, "kind": "video", "title": "奶蛙日常", "url": "https://cdn.public.test/frog.mp4",
             "local_path": "", "source_url": "https://public.test/post", "source_name": "public.test",
             "sha256": digest, "rights": "permission", "evidence": "Existing permission record",
             "credit": "Original source", "reviewed": True, "ai_generated": False, "added_at": NOW.isoformat()}
    asset.update(updates)
    store.data["assets"][identity] = asset
    return asset


def candidate(store, identity="candidate:one"):
    asset = {"id": identity, "kind": "candidate", "title": "奶蛙视频", "url": "",
             "source_url": "https://public.test/" + identity.replace(":", "/"),
             "search_excerpt": "Naiwa daily video", "sha256": "", "rights": "pending",
             "evidence": "", "credit": "", "reviewed": False, "ai_generated": False,
             "added_at": NOW.isoformat()}
    store.data["assets"][identity] = asset
    return asset


def recently_used(store, asset):
    store.data["jobs"]["story:2026-10-22"] = {
        "channel": "story", "kind": "video", "asset_id": asset["id"], "sha256": asset["sha256"],
        "status": "published", "published_at": NOW.isoformat()}


def fake_download(monkeypatch, content=b"test MP4 bytes"):
    calls = []
    def download(_client, url, target):
        calls.append(url)
        target.write_bytes(content)
    monkeypatch.setattr(auto_video, "download", download)
    monkeypatch.setattr(auto_video, "validate_web_video", lambda _: None)
    monkeypatch.setattr(auto_video, "find_video", lambda *_: "https://cdn.public.test/frog.mp4")
    return calls


def fail_if_called(*_args, **_kwargs):
    raise AssertionError("This operation should not run")


def test_existing_story_stock_does_not_search_or_download(cfg, store, tmp_path, monkeypatch):
    video(store)
    monkeypatch.setattr(auto_video, "discover", fail_if_called)
    monkeypatch.setattr(auto_video, "find_video", fail_if_called)
    monkeypatch.setattr(auto_video, "download", fail_if_called)
    assert auto_video.replenish_from_web(cfg, store, None, NOW, tmp_path / "scratch") == {
        "status": "stock_available"}
    assert not store.data["discovery"]


def test_rejected_candidate_is_not_automatically_imported(cfg, store, tmp_path, monkeypatch):
    item = candidate(store)
    item["rights"] = "rejected"
    monkeypatch.setattr(auto_video, "discover", lambda *_: "already searched")
    monkeypatch.setattr(auto_video, "find_video", fail_if_called)
    assert auto_video.replenish_from_web(cfg, store, None, NOW, tmp_path / "scratch")["status"] == "no_usable_video"
    assert store.data["assets"] == {item["id"]: item}


def test_search_page_download_decode_import_and_daily_limit(cfg, store, tmp_path, valid_mp4):
    requests = []
    def handler(request):
        requests.append((request.method, request.url.host, request.url.path))
        if request.url.host == "api.tavily.com":
            assert request.headers["authorization"] == "Bearer test-search-key"
            return httpx.Response(200, json={"results": [{"title": "奶蛙日常视频",
                "url": "https://public.test/post", "content": "Naiwa clip"}]})
        if request.url.host == "public.test":
            assert "authorization" not in request.headers
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  text='<video><source src="https://cdn.public.test/frog.mp4"></video>')
        if request.url.host == "cdn.public.test":
            return httpx.Response(200, headers={"content-type": "video/mp4"}, content=valid_mp4)
        raise AssertionError("Unexpected network request")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = auto_video.replenish_from_web(cfg, store, client, NOW, tmp_path / "scratch")
        assert result["status"] == "imported"
        imported = store.data["assets"][result["asset_id"]]
        assert imported["rights"] == "unverified"
        assert imported["approval_mode"] == "automatic_operator_policy"
        assert imported["evidence"] == cfg.discovery["operator_policy"]
        assert imported["source_url"] == "https://public.test/post"
        assert imported["credit"] == "Source: public.test"
        assert imported["ai_generated"] is False and imported["ai_origin"] == "unknown"
        assert (store.path / imported["state_path"]).read_bytes() == valid_mp4
        assert imported["sha256"] == hashlib.sha256(valid_mp4).hexdigest()
        assert [asset["id"] for asset in eligible(store, "story", NOW, 30)] == [imported["id"]]
        # While stock is available no additional source is looked up.
        assert auto_video.replenish_from_web(cfg, store, client, NOW, tmp_path / "scratch")["status"] == "stock_available"
        recently_used(store, imported)
        assert auto_video.replenish_from_web(cfg, store, client, NOW, tmp_path / "scratch")["status"] == "daily_import_limit"
    assert requests == [("POST", "api.tavily.com", "/search"), ("GET", "public.test", "/post"),
                        ("GET", "cdn.public.test", "/frog.mp4")]
    assert not list((tmp_path / "scratch").glob("*"))
    assert not store.data["ai_requests"]


def test_duplicate_source_hash_is_not_imported(cfg, store, tmp_path, monkeypatch):
    content = b"same existing source bytes"
    video(store, digest=hashlib.sha256(content).hexdigest(), rights="pending", reviewed=False)
    item = candidate(store)
    monkeypatch.setattr(auto_video, "discover", lambda *_: "already searched")
    downloads = fake_download(monkeypatch, content)
    monkeypatch.setattr(auto_video, "validate_web_video", fail_if_called)
    result = auto_video.replenish_from_web(cfg, store, None, NOW, tmp_path / "scratch")
    assert result["status"] == "no_usable_video"
    assert item["auto_status"] == "duplicate"
    assert len(downloads) == 1 and len(store.data["assets"]) == 2
    assert not list((store.path / "media").iterdir())
    assert not list((tmp_path / "scratch").iterdir())


def test_daily_candidate_limit_and_queries_are_not_repeated(cfg, store, tmp_path, monkeypatch):
    cfg.discovery["max_candidate_checks_per_day"] = 2
    searches, checked = [], []
    def handler(request):
        searches.append(request)
        return httpx.Response(200, json={"results": [{"title": "奶蛙视频", "url": f"https://public.test/{n}"}
                                                   for n in range(4)]})
    def no_video(_client, source):
        checked.append(source)
        return None
    monkeypatch.setattr(auto_video, "find_video", no_video)
    monkeypatch.setattr(auto_video, "download", fail_if_called)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        first = auto_video.replenish_from_web(cfg, store, client, NOW, tmp_path / "scratch")
        second = auto_video.replenish_from_web(cfg, store, client, NOW, tmp_path / "scratch")
    assert first["checked"] == second["checked"] == 2
    assert len(searches) == 1 and len(checked) == len(set(checked)) == 2
    assert len(store.data["discovery"][DAY]["auto_import"]["checked_ids"]) == 2
    assert not list((store.path / "media").iterdir())


@pytest.mark.parametrize("failure", ["no_direct_link", "invalid_mp4", "partial_download"])
def test_unusable_candidate_never_enters_media_and_temp_is_cleaned(cfg, store, tmp_path, monkeypatch, failure):
    item = candidate(store)
    monkeypatch.setattr(auto_video, "discover", lambda *_: "already searched")
    monkeypatch.setattr(auto_video, "find_video", lambda *_: None if failure == "no_direct_link" else "https://cdn.public.test/frog.mp4")
    def download(_client, _url, target):
        target.write_bytes(b"not an MP4 file")
        if failure == "partial_download":
            raise RemoteError("Download interrupted")
    monkeypatch.setattr(auto_video, "download", download)
    result = auto_video.replenish_from_web(cfg, store, None, NOW, tmp_path / "scratch")
    assert result["status"] == "no_usable_video"
    assert item["auto_status"] == ("no_public_mp4" if failure == "no_direct_link" else "unavailable")
    assert not eligible(store, "story", NOW, 30)
    assert not list((store.path / "media").iterdir())
    assert not list((tmp_path / "scratch").iterdir())


def test_unverified_requires_explicit_operator_policy_mode(store):
    asset = video(store, rights="unverified")
    assert not publishable(asset)
    assert not eligible(store, "story", NOW, 30)
    asset["approval_mode"] = "manual"
    assert not publishable(asset)
    asset["approval_mode"] = "automatic_operator_policy"
    assert publishable(asset)
    assert eligible(store, "story", NOW, 30) == [asset]


class FakeInstagram:
    def __init__(self, store):
        self.store = store
        self.creates = 0
        self.publishes = 0

    def create(self, job, _asset, _url):
        assert self.store.snapshots[-1]["jobs"][SLOT]["status"] == "creating"
        self.creates += 1
        return "container-1"

    def status(self, _container):
        return "FINISHED"

    def publish(self, _container):
        assert self.store.snapshots[-1]["jobs"][SLOT]["status"] == "publishing"
        self.publishes += 1
        return "published-1"


def prepared(_config, _store, _client, asset, _channel, _scratch):
    return "media/" + asset["sha256"] + ".mp4", asset["sha256"]


def publish_story(cfg, store, ig, scratch, client=None):
    return engine.publish_slot(cfg, store, client, ig, SLOT, "story", NOW, scratch,
                               preparer=prepared, preflight=lambda *_: None)


def test_story_uses_existing_stock_without_searching(cfg, store, tmp_path, monkeypatch):
    video(store)
    monkeypatch.setattr(engine, "replenish_from_web", fail_if_called)
    monkeypatch.setattr(engine, "generate_video", fail_if_called)
    ig = FakeInstagram(store)
    assert publish_story(cfg, store, ig, tmp_path / "scratch") == "published"
    assert ig.creates == ig.publishes == 1


def test_empty_story_imports_and_publishes_once(cfg, store, tmp_path, monkeypatch):
    item = candidate(store)
    searches = []
    monkeypatch.setattr(auto_video, "discover", lambda *_: searches.append("search"))
    downloads = fake_download(monkeypatch)
    monkeypatch.setattr(engine, "generate_video", fail_if_called)
    ig = FakeInstagram(store)
    assert publish_story(cfg, store, ig, tmp_path / "scratch") == "published"
    assert publish_story(cfg, store, ig, tmp_path / "scratch") == "published"
    assert searches == ["search"] and len(downloads) == 1
    assert ig.creates == ig.publishes == 1
    assert store.data["jobs"][SLOT]["asset_id"] == item["auto_asset_id"]
    assert store.data["assets"][item["auto_asset_id"]]["rights"] == "unverified"


def test_empty_feed_does_not_trigger_story_replenishment(cfg, store, tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "replenish_from_web", fail_if_called)
    monkeypatch.setattr(engine, "generate_video", fail_if_called)
    ig = FakeInstagram(store)
    assert engine.publish_slot(cfg, store, None, ig, "feed:" + DAY, "feed", NOW, tmp_path / "scratch",
                               preparer=prepared, preflight=lambda *_: None) == "blocked"
    assert ig.creates == ig.publishes == 0


def test_disabled_ai_never_requests_generation_when_search_finds_nothing(cfg, store, tmp_path):
    requests = []
    def handler(request):
        requests.append(request.url.host)
        assert request.url.host == "api.tavily.com", "AI generation must stay disabled"
        return httpx.Response(200, json={"results": []})
    ig = FakeInstagram(store)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert publish_story(cfg, store, ig, tmp_path / "scratch", client) == "blocked"
    assert requests == ["api.tavily.com"]
    assert not store.data["ai_requests"]
    assert ig.creates == ig.publishes == 0


def test_import_journal_save_failure_stops_before_instagram(cfg, store, tmp_path, monkeypatch):
    item = candidate(store)
    monkeypatch.setattr(auto_video, "discover", lambda *_: "already searched")
    fake_download(monkeypatch)
    original_save = store.save
    def fail_after_import():
        if any(asset.get("approval_mode") == "automatic_operator_policy" for asset in store.data["assets"].values()):
            raise RuntimeError("Simulated state push failure")
        original_save()
    monkeypatch.setattr(store, "save", fail_after_import)
    ig = FakeInstagram(store)
    with pytest.raises(RuntimeError, match="state push failure"):
        publish_story(cfg, store, ig, tmp_path / "scratch")
    assert item["auto_status"] == "imported"  # A persistence failure is not a media validation failure.
    assert not store.data["jobs"]
    assert ig.creates == ig.publishes == 0
