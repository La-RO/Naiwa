import copy
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from urllib.parse import parse_qs

from cryptography.fernet import Fernet
import httpx
import pytest

from naiwa_bot.auto_video import replenish_from_web
from naiwa_bot.catalogue import eligible, import_catalogue
from naiwa_bot.config import Config
from naiwa_bot.engine import publish_slot
from naiwa_bot.providers import Instagram, discover
from naiwa_bot.state import Store


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 24, 2, 30, tzinfo=timezone.utc)
SLOT = "story:2026-10-24"
GALLERIES = ("sanctuary-tour", "wallpaper-tunnel", "laughing-gallery")


class RecordingStore(Store):
    def __init__(self, path):
        super().__init__(path)
        self.snapshots = []
        self.saved_media = []

    def save(self):
        self.saved_media.append(tuple(sorted(path.name for path in (self.path / "media").iterdir())))
        super().save()
        self.snapshots.append(copy.deepcopy(self.data))

    def public_url(self, relative):
        return "https://example.com/" + relative


@pytest.fixture
def cfg():
    value = Config.load(ROOT)
    value.ai.update(enabled=False)
    value.discovery.update(enabled=True, auto_publish=True, queries=["Naiwa video"])
    return value


@pytest.fixture
def store(tmp_path):
    value = RecordingStore(tmp_path / "state")
    value.data.update(paused=False, start_date="2026-10-24")
    return value


def insert(store, identity="clip", kind="video", **changes):
    asset = {
        "id": identity, "kind": kind, "title": "Naiwa",
        "source_url": "https://example.com/source", "url": "https://example.com/clip.mp4",
        "local_path": "", "rights": "permission", "evidence": "Operator permission record",
        "credit": "Creator", "reviewed": True, "ai_generated": False,
        "sha256": hashlib.sha256(identity.encode()).hexdigest(), "added_at": NOW.isoformat(),
    }
    asset.update(changes)
    store.data["assets"][identity] = asset
    return asset


class FakeIG:
    def __init__(self):
        self.creates = []
        self.statuses = []
        self.publishes = []

    def create(self, job, asset, url):
        self.creates.append((copy.deepcopy(job), copy.deepcopy(asset), url))
        return "new-container"

    def status(self, identity):
        self.statuses.append(identity)
        return "FINISHED"

    def publish(self, identity):
        self.publishes.append(identity)
        return "123456"


def prepared(config, store, client, asset, channel, scratch):
    suffix = ".mp4" if asset["kind"] == "video" else ".jpg"
    return "media/" + asset["sha256"] + suffix, asset["sha256"]


def process(cfg, store, ig, tmp_path, channel="story"):
    slot = SLOT if channel == "story" else "feed:2026-10-24"
    return publish_slot(cfg, store, None, ig, slot, channel, NOW, tmp_path / "scratch",
                        preparer=prepared, preflight=lambda *_: None)


def no_ai(*_):
    pytest.fail("AI generation was not permitted for this search result")


def test_existing_gallery_assets_migrate_without_losing_permission(cfg, store):
    for name in GALLERIES:
        insert(store, "repo:" + name)
    assert import_catalogue(store, ROOT) == 24
    for name in GALLERIES:
        asset = store.data["assets"]["repo:" + name]
        assert asset["video_style"] in ("slideshow", "pan_zoom", "still")
        assert asset["rights"] == "permission" and asset["reviewed"]
        assert asset["evidence"] == "Operator permission record"
    assert eligible(store, "story", NOW, 30) == []
    assert eligible(store, "feed", NOW, 30) == []


def test_gallery_waiting_container_is_never_published(cfg, store, tmp_path, monkeypatch):
    insert(store, "repo:sanctuary-tour", video_style="slideshow")
    store.data["jobs"][SLOT] = {
        "channel": "story", "kind": "video", "status": "waiting", "attempts": 1,
        "asset_id": "repo:sanctuary-tour", "prepared_path": "media/old.mp4",
        "media_url": "https://example.com/old.mp4", "container_id": "old-container",
    }
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", lambda *_: {"status": "search_unavailable"})
    monkeypatch.setattr("naiwa_bot.engine.generate_video", no_ai)
    ig = FakeIG()
    assert process(cfg, store, ig, tmp_path) == "blocked"
    assert not ig.creates and not ig.statuses and not ig.publishes


def test_interrupted_gallery_publish_remains_needs_review(cfg, store, tmp_path, monkeypatch):
    insert(store, "repo:sanctuary-tour", video_style="slideshow")
    store.data["jobs"][SLOT] = {
        "channel": "story", "kind": "video", "status": "publishing", "attempts": 1,
        "asset_id": "repo:sanctuary-tour", "container_id": "old-container",
    }
    monkeypatch.setattr("naiwa_bot.engine.generate_video", no_ai)
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", no_ai)
    ig = FakeIG()
    assert process(cfg, store, ig, tmp_path) == "needs_review"
    assert not ig.creates and not ig.statuses and not ig.publishes
    assert store.data["jobs"][SLOT]["container_id"] == "old-container"


@pytest.fixture
def api(cfg, store, monkeypatch):
    monkeypatch.setenv("BOT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("IG_ACCESS_TOKEN", "dummy-instagram-token")
    monkeypatch.setenv("IG_USER_ID", "42")
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"id": "container"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    yield Instagram(cfg, store, client), requests
    client.close()


@pytest.mark.parametrize("kind", ["image", "video"])
def test_feed_payload_matches_actual_media_kind(store, api, kind):
    ig, requests = api
    asset = insert(store, kind=kind)
    ig.create({"channel": "feed", "kind": kind}, asset, "https://example.com/published")
    assert len(requests) == 1
    payload = parse_qs(requests[0].content.decode())
    if kind == "image":
        assert payload["image_url"] == ["https://example.com/published"]
        assert "video_url" not in payload and "media_type" not in payload
    else:
        assert payload["video_url"] == ["https://example.com/published"]
        assert payload["media_type"] == ["REELS"] and payload["share_to_feed"] == ["true"]
        assert "image_url" not in payload


@pytest.mark.parametrize("kind,channel,job_kind,style", [
    ("image", "story", "image", None),
    ("image", "feed", "video", None),
    ("video", "feed", "image", None),
    ("video", "feed", "video", "slideshow"),
])
def test_invalid_media_job_never_reaches_instagram(store, api, kind, channel, job_kind, style):
    ig, requests = api
    asset = insert(store, kind=kind, video_style=style)
    with pytest.raises(ValueError):
        ig.create({"channel": channel, "kind": job_kind}, asset, "https://example.com/clip")
    assert requests == []


def test_web_imported_video_publishes_without_ai(cfg, store, tmp_path, monkeypatch):
    calls = []
    def web(*_):
        calls.append("web")
        insert(store, "web:found", video_style="motion")
        return {"status": "imported"}
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", web)
    monkeypatch.setattr("naiwa_bot.engine.generate_video", no_ai)
    ig = FakeIG()
    assert process(cfg, store, ig, tmp_path) == "published"
    assert process(cfg, store, ig, tmp_path) == "published"
    assert calls == ["web"] and len(ig.publishes) == 1
    assert ig.creates[0][1]["id"] == "web:found"


def test_only_confirmed_absence_of_web_video_allows_ai(cfg, store, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", lambda *_: {"status": "no_usable_video"})
    def generated(*_):
        calls.append("ai")
        return insert(store, "ai:fallback", ai_generated=True, rights="ai", video_style="motion")
    monkeypatch.setattr("naiwa_bot.engine.generate_video", generated)
    ig = FakeIG()
    assert process(cfg, store, ig, tmp_path) == "published"
    assert process(cfg, store, ig, tmp_path) == "published"
    assert calls == ["ai"] and len(ig.publishes) == 1


@pytest.mark.parametrize("status", ["search_unavailable", "scan_unavailable", "daily_import_limit",
                                   "automatic_import_disabled", "not_attempted"])
def test_incomplete_web_search_never_triggers_paid_ai(cfg, store, tmp_path, monkeypatch, status):
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", lambda *_: {"status": status})
    monkeypatch.setattr("naiwa_bot.engine.generate_video", no_ai)
    ig = FakeIG()
    assert process(cfg, store, ig, tmp_path) == "blocked"
    assert not ig.creates and not ig.publishes


def test_web_timeout_never_triggers_paid_ai(cfg, store, tmp_path, monkeypatch):
    def timeout(*_):
        raise httpx.ReadTimeout("simulated public search timeout")
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", timeout)
    monkeypatch.setattr("naiwa_bot.engine.generate_video", no_ai)
    ig = FakeIG()
    with pytest.raises(httpx.ReadTimeout):
        process(cfg, store, ig, tmp_path)
    assert not ig.creates and not ig.publishes


def test_failed_search_query_cannot_later_appear_completed(cfg, store, tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "dummy-search-key")
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout("simulated search timeout")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadTimeout):
            discover(cfg, store, client, NOW)
        record = store.data["discovery"][NOW.astimezone(cfg.timezone).date().isoformat()]
        assert record["query_status"] == {"Naiwa video": "failed_or_unknown"}
        result = replenish_from_web(cfg, store, client, NOW, tmp_path / "search")
    assert len(calls) == 1 and result["status"] == "search_unavailable"
    assert record["query_status"]["Naiwa video"] == "failed_or_unknown"
