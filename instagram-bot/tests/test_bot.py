import base64
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from cryptography.fernet import Fernet
import httpx
from PIL import Image
import pytest
import imageio_ffmpeg

from naiwa_bot.catalogue import add_asset, approve, eligible, import_catalogue
from naiwa_bot.config import Config, inside
from naiwa_bot.engine import due_slots, preview, publish_slot, run
from naiwa_bot.media import overlay, prepare
from naiwa_bot.network import download, validate_public_url
from naiwa_bot.providers import Instagram, caption, discover, generate_video, oauth_exchange
from naiwa_bot.state import Store
from naiwa_bot.__main__ import execute


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 22, 8, 30, tzinfo=timezone.utc)  # 19:30 Sydney


@pytest.fixture
def cfg():
    return Config.load(ROOT)


class MemoryStore(Store):
    def __init__(self, path):
        super().__init__(path)
        self.snapshots = []
        self.fail_on = None

    def save(self):
        if self.fail_on == len(self.snapshots) + 1:
            raise RuntimeError("simulated push failure")
        super().save()
        self.snapshots.append(copy.deepcopy(self.data))

    def public_url(self, relative):
        return "https://example.com/" + relative


@pytest.fixture
def store(tmp_path):
    value = MemoryStore(tmp_path / "state")
    value.data["paused"] = False
    value.data["start_date"] = "2026-10-22"
    return value


def insert(store, name="clip", kind="video", digest="a" * 64):
    asset = {"id": name, "kind": kind, "title": "奶蛙", "url": "https://example.com/clip.mp4",
             "local_path": "", "source_url": "https://example.com/source", "rights": "permission",
             "evidence": "Permission record A", "credit": "Original Creator", "reviewed": True,
             "sha256": digest, "ai_generated": False, "added_at": NOW.isoformat()}
    store.data["assets"][name] = asset
    return asset


class FakeIG:
    def __init__(self, store, timeout=False):
        self.store, self.timeout = store, timeout
        self.creates, self.publishes = 0, 0
        self.container_status = "FINISHED"

    def create(self, job, asset, url):
        assert self.store.snapshots[-1]["jobs"]["story:2026-10-22"]["status"] == "creating"
        self.creates += 1
        return "container123"

    def status(self, container):
        return self.container_status

    def publish(self, container):
        assert self.store.snapshots[-1]["jobs"]["story:2026-10-22"]["status"] == "publishing"
        self.publishes += 1
        if self.timeout:
            raise httpx.ReadTimeout("server accepted, reply lost")
        return "123456"


def prepared(config, store, client, asset, channel, scratch):
    return "media/" + "b" * 64 + ".mp4", asset["sha256"]


def process(cfg, store, ig, tmp_path):
    return publish_slot(cfg, store, None, ig, "story:2026-10-22", "story", NOW, tmp_path,
                        preparer=prepared, preflight=lambda *_: None)


def test_real_catalogue_import_is_idempotent_and_pending(cfg, store):
    assert import_catalogue(store, cfg.root) == 27
    assert import_catalogue(store, cfg.root) == 0
    assert len(store.data["assets"]) == 27
    assert eligible(store, "story", NOW, 30) == []
    assert all(a["rights"] == "pending" for a in store.data["assets"].values())


def test_approval_requires_evidence_and_credit(store):
    insert(store)
    with pytest.raises(ValueError):
        approve(store, {"asset_ids": ["clip"], "rights": "permission"})
    approve(store, {"asset_ids": ["clip"], "rights": "permission", "evidence": "recordA", "credit": "creator"})
    assert len(eligible(store, "story", NOW, 30)) == 1


def test_unapproved_and_ai_misclassified_content_blocked(store):
    asset = insert(store)
    asset.update(ai_generated=True, reviewed=False, rights="pending")
    assert not eligible(store, "story", NOW, 30)
    with pytest.raises(ValueError):
        approve(store, {"asset_ids": ["clip"], "rights": "owned", "evidence": "record", "credit": "me"})


def test_story_is_video_only_and_feed_alternates(store):
    insert(store, "image", "image", "b" * 64)
    insert(store)
    assert [a["id"] for a in eligible(store, "story", NOW, 30)] == ["clip"]
    assert eligible(store, "feed", NOW, 30)[0]["kind"] == "video"
    store.data["jobs"]["old"] = {"channel": "feed", "kind": "video", "status": "published", "asset_id": "old", "published_at": "2026-08-01T00:00:00+00:00"}
    assert eligible(store, "feed", NOW, 30)[0]["kind"] == "image"


def test_schedule_every_three_local_calendar_days(cfg, store):
    assert len(due_slots(cfg, store.data, NOW)) == 2
    assert len(due_slots(cfg, store.data, NOW.replace(day=23))) == 1
    assert len(due_slots(cfg, store.data, NOW.replace(day=25))) == 2
    # Month rollover is calendar arithmetic, not day-of-month modulo.
    store.data["start_date"] = "2026-10-31"
    assert len(due_slots(cfg, store.data, NOW.replace(month=11, day=3))) == 2


def test_dst_and_no_historical_backfill(cfg, store):
    store.data["start_date"] = "2026-10-03"
    before_dst = datetime(2026, 10, 3, 1, 59, tzinfo=timezone.utc)
    after_dst = datetime(2026, 10, 4, 1, 0, tzinfo=timezone.utc)
    assert due_slots(cfg, store.data, before_dst) == []  # 11:59 AEST
    assert due_slots(cfg, store.data, after_dst) == [("story:2026-10-04", "story")]  # 12:00 AEDT
    assert all("2026-10-22" in slot for slot, _ in due_slots(cfg, store.data, NOW))


def test_preview_does_not_consume_slots_or_save(cfg, store):
    insert(store)
    before = copy.deepcopy(store.data)
    result = preview(cfg, store, NOW)
    assert result[0]["asset_id"] == "clip"
    assert result[1]["asset_id"] is None
    assert store.data == before and store.snapshots == []


def test_success_is_idempotent_and_journal_precedes_publish(cfg, store, tmp_path):
    insert(store)
    ig = FakeIG(store)
    assert process(cfg, store, ig, tmp_path) == "published"
    assert process(cfg, store, ig, tmp_path) == "published"
    assert ig.creates == 1 and ig.publishes == 1
    assert store.data["jobs"]["story:2026-10-22"]["media_id"] == "123456"


def test_publish_timeout_never_automatically_retries(cfg, store, tmp_path):
    insert(store)
    ig = FakeIG(store, timeout=True)
    assert process(cfg, store, ig, tmp_path) == "needs_review"
    assert process(cfg, store, ig, tmp_path) == "needs_review"
    assert ig.publishes == 1
    assert not eligible(store, "feed", NOW, 30)


def test_interrupted_publish_requires_review(cfg, store, tmp_path):
    insert(store)
    store.data["jobs"]["story:2026-10-22"] = {"status": "publishing", "channel": "story", "asset_id": "clip"}
    ig = FakeIG(store)
    assert process(cfg, store, ig, tmp_path) == "needs_review"
    assert ig.publishes == 0


def test_persistence_failure_prevents_live_call(cfg, store, tmp_path):
    insert(store)
    ig = FakeIG(store)
    store.fail_on = 3
    with pytest.raises(RuntimeError):
        process(cfg, store, ig, tmp_path)
    assert ig.creates == 0 and ig.publishes == 0


def test_waiting_reuses_container_without_spending_attempts(cfg, store, tmp_path):
    insert(store)
    ig = FakeIG(store)
    ig.container_status = "IN_PROGRESS"
    for _ in range(4):
        assert process(cfg, store, ig, tmp_path) == "waiting"
    ig.container_status = "FINISHED"
    assert process(cfg, store, ig, tmp_path) == "published"
    assert ig.creates == 1 and ig.publishes == 1


def test_content_hash_deduplicates_different_ids(cfg, store, tmp_path):
    insert(store)
    ig = FakeIG(store)
    assert process(cfg, store, ig, tmp_path) == "published"
    insert(store, "different-url-same-bytes")
    assert not eligible(store, "feed", NOW, 30)


def test_explicit_rejected_asset_never_publishes(cfg, store, tmp_path):
    asset = insert(store)
    asset.update(rights="rejected", reviewed=False)
    ig = FakeIG(store)
    assert process(cfg, store, ig, tmp_path) == "blocked"
    assert ig.publishes == 0


def test_pause_disables_all_network_calls(cfg, store, tmp_path):
    store.data["paused"] = True
    def forbidden(*args):
        raise AssertionError("Paused bot tried to connect")
    assert run(cfg, store, None, NOW, tmp_path, ig_factory=forbidden) == {"paused": True}


def test_image_converts_webp_to_instagram_jpeg(cfg, store, tmp_path):
    import_catalogue(store, cfg.root)
    asset = next(a for a in store.data["assets"].values() if a["kind"] == "image")
    asset["credit"] = "Original Creator"
    relative, digest = prepare(cfg, store, None, asset, "feed", tmp_path / "scratch")
    with Image.open(store.path / relative) as image:
        assert image.format == "JPEG" and image.size == (1080, 1350)
    assert digest == asset["sha256"]


def test_actual_video_transcode_and_ai_disclosure(cfg, store, tmp_path):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    source = store.path / "media/source.mp4"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=yellow:s=320x240:r=24", "-t", "3", "-c:v", "libx264", str(source)], check=True)
    asset = insert(store, digest="")
    asset.update(state_path="media/source.mp4", ai_generated=True)
    relative, _ = prepare(cfg, store, None, asset, "story", tmp_path / "scratch")
    assert (store.path / relative).stat().st_size > 1000
    frame = tmp_path / "frame.png"
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(store.path / relative), "-frames:v", "1", str(frame)], check=True)
    with Image.open(frame) as image:
        assert image.size == (1080, 1920)
        assert image.getpixel((5, 1650))[0] < 150  # burned-in disclosure background
    assert "AI-generated fictional" in caption(asset)


def test_path_traversal_and_private_urls_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        inside(tmp_path, "../secret")
    for url in ("http://example.com/a", "https://127.0.0.1/a", "https://user:password@example.com/a", "https://[::1]/a"):
        with pytest.raises(ValueError):
            validate_public_url(url)


def test_download_redirects_revalidate_destination(monkeypatch, tmp_path):
    monkeypatch.setattr("naiwa_bot.network.socket.getaddrinfo", lambda host, *args, **kwargs: [(None,None,None,None,("127.0.0.1" if host == "private.test" else "8.8.8.8",443))])
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://private.test/file"})))
    with pytest.raises(ValueError):
        download(client, "https://public.test/file", tmp_path / "file")


def test_instagram_payloads_encryption_and_correct_account(cfg, store, monkeypatch):
    monkeypatch.setenv("BOT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("IG_ACCESS_TOKEN", "secret-token")
    requests = []
    def handler(req):
        requests.append(req)
        if req.url.path.endswith("/me"):
            return httpx.Response(200, json={"user_id": "123", "username": "unimelb.naiwaclub", "account_type": "BUSINESS"})
        return httpx.Response(200, json={"id": "456"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ig = Instagram(cfg, store, client)
    ig.verify(NOW)
    assert "secret-token" not in json.dumps(store.data)
    asset = insert(store)
    ig.create({"channel": "story"}, asset, "https://example.com/a.mp4")
    assert b"media_type=STORIES" in requests[-1].content and b"caption" not in requests[-1].content
    ig.create({"channel": "feed"}, asset, "https://example.com/a.mp4")
    assert b"media_type=REELS" in requests[-1].content


def test_wrong_account_is_rejected(cfg, store, monkeypatch):
    monkeypatch.setenv("BOT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("IG_ACCESS_TOKEN", "secret-token")
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"user_id":"123", "username":"other", "account_type":"BUSINESS"})))
    with pytest.raises(ValueError, match="different username"):
        Instagram(cfg, store, client).verify(NOW)


def test_check_connects_while_paused_without_publishing(cfg, store, monkeypatch, tmp_path):
    key = Fernet.generate_key()
    monkeypatch.setenv("BOT_ENCRYPTION_KEY", key.decode())
    monkeypatch.setenv("IG_ACCESS_TOKEN", "check-secret-token")
    monkeypatch.setenv("IG_USER_ID", "123")
    store.data["paused"] = True
    before = copy.deepcopy(store.data)
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET" and request.url.path.endswith("/me")
        return httpx.Response(200, json={"user_id": "123", "username": "unimelb.naiwaclub", "account_type": "BUSINESS"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute("check", {}, cfg, store, client, NOW, tmp_path / "scratch")
    assert result == {"connected": True, "account": {"user_id": "123", "username": "unimelb.naiwaclub", "account_type": "BUSINESS"},
                      "paused": True, "publishing_tested": False}
    assert len(requests) == 1
    assert not (tmp_path / "scratch").exists()
    for field in before:
        if field != "account":
            assert store.data[field] == before[field]
    assert "check-secret-token" not in json.dumps(result) + json.dumps(store.data)
    assert Fernet(key).decrypt(store.data["account"]["encrypted_token"].encode()).decode() == "check-secret-token"


@pytest.mark.parametrize("info,error", [
    ({"user_id": "123", "username": "other", "account_type": "BUSINESS"}, "different username"),
    ({"user_id": "456", "username": "unimelb.naiwaclub", "account_type": "BUSINESS"}, "IG_USER_ID"),
    ({"user_id": "123", "username": "unimelb.naiwaclub", "account_type": "MEDIA_CREATOR"}, "Business account"),
])
def test_check_rejects_account_mismatch_without_saving(cfg, store, monkeypatch, tmp_path, info, error):
    monkeypatch.setenv("BOT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("IG_ACCESS_TOKEN", "check-secret-token")
    monkeypatch.setenv("IG_USER_ID", "123")
    store.data["paused"] = True
    before = copy.deepcopy(store.data)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=info)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError, match=error):
            execute("check", {}, cfg, store, client, NOW, tmp_path / "scratch")
    assert len(requests) == 1 and requests[0].method == "GET"
    assert store.data == before and store.snapshots == []


def test_discovery_calls_once_per_query_per_day(cfg, store, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={"results":[{"title":"奶蛙视频", "url":"https://example.com/source"}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    discover(cfg, store, client, NOW)
    discover(cfg, store, client, NOW)
    assert len(calls) == 3 and len(store.data["assets"]) == 1
    candidate = next(iter(store.data["assets"].values()))
    assert candidate["kind"] == "candidate" and candidate["rights"] == "pending"


def test_ai_daily_cap_includes_unknown_requests(cfg, store, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    cfg.ai.update(enabled=True, character_rights_confirmed=True, reference_image="assets/gallery/l-18.webp")
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("timeout")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError):
        generate_video(cfg, store, client, NOW)
    assert generate_video(cfg, store, client, NOW) is None
    assert len(calls) == 1


def test_ai_rest_steps_are_parsed_and_await_review(cfg, store, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    cfg.ai.update(enabled=True, character_rights_confirmed=True, reference_image="assets/gallery/l-18.webp", auto_approve=False)
    response = {"status":"completed", "steps":[{"type":"model_output", "content":[{"type":"video", "data":base64.b64encode(b"fake-video-bytes").decode()}]}]}
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200,json=response)))
    asset = generate_video(cfg, store, client, NOW)
    assert asset["ai_generated"] and asset["rights"] == "pending" and not asset["reviewed"]
    assert not eligible(store, "story", NOW, 30)


def test_oauth_rejects_csrf_before_network(cfg, store, monkeypatch):
    store.data["oauth"] = {"hash":"wrong", "created_at":NOW.isoformat()}
    monkeypatch.setenv("IG_OAUTH_STATE", "not-matching")
    with pytest.raises(ValueError, match="state mismatch"):
        oauth_exchange(cfg, store, None, NOW)


def test_final_persistence_failure_recovers_without_duplicate(cfg, store, tmp_path):
    insert(store)
    ig = FakeIG(store)
    # Discover the number of saves before the last publication acknowledgment.
    original_save = store.save
    def fail_final_save():
        if store.data["jobs"].get("story:2026-10-22", {}).get("status") == "published":
            raise RuntimeError("acknowledgment push failed")
        original_save()
    store.save = fail_final_save
    with pytest.raises(RuntimeError):
        process(cfg, store, ig, tmp_path)
    assert ig.publishes == 1
    store.data = copy.deepcopy(store.snapshots[-1])
    store.save = original_save
    assert process(cfg, store, ig, tmp_path) == "needs_review"
    assert ig.publishes == 1


def test_container_already_published_requires_reconciliation(cfg, store, tmp_path):
    insert(store)
    ig = FakeIG(store)
    ig.container_status = "PUBLISHED"
    assert process(cfg, store, ig, tmp_path) == "needs_review"
    assert ig.publishes == 0


def test_prepublication_failures_have_a_retry_limit(cfg, store, tmp_path):
    insert(store)
    ig = FakeIG(store)
    ig.container_status = "ERROR"
    for _ in range(5):
        assert process(cfg, store, ig, tmp_path) == "failed"
    assert ig.creates == 3 and ig.publishes == 0


def test_abandoned_unknown_publish_keeps_hash_quarantined(cfg, store):
    from naiwa_bot.__main__ import execute
    insert(store)
    store.data["jobs"]["story:2026-10-22"] = {"status":"needs_review", "channel":"story", "asset_id":"clip", "sha256":"a"*64}
    execute("abandon", {"slot":"story:2026-10-22", "evidence":"inspection recorded"}, cfg, store, None, NOW, Path("."))
    insert(store, "same-bytes-another-url")
    assert not eligible(store, "story", NOW, 30)


def test_reconcile_is_explicit_and_unknown_is_not_retryable(cfg, store):
    from naiwa_bot.__main__ import execute
    insert(store)
    store.data["jobs"]["story:2026-10-22"] = {"status":"needs_review", "channel":"story", "asset_id":"clip"}
    with pytest.raises(ValueError):
        execute("retry", {"slot":"story:2026-10-22"}, cfg, store, None, NOW, Path("."))
    execute("reconcile", {"slot":"story:2026-10-22", "media_id":"12345", "evidence":"checked on account"}, cfg, store, None, NOW, Path("."))
    assert store.data["jobs"]["story:2026-10-22"]["status"] == "published"


def test_revoking_authorization_stops_reserved_container(cfg, store, tmp_path):
    asset = insert(store)
    ig = FakeIG(store)
    ig.container_status = "IN_PROGRESS"
    assert process(cfg, store, ig, tmp_path) == "waiting"
    asset.update(rights="rejected", reviewed=False)
    assert process(cfg, store, ig, tmp_path) == "blocked"
    assert ig.publishes == 0


def test_download_size_limit_cleans_up_partial(monkeypatch, tmp_path):
    monkeypatch.setattr("naiwa_bot.network.validate_public_url", lambda _: None)
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * 100)))
    destination = tmp_path / "download"
    with pytest.raises(ValueError, match="size limit"):
        download(client, "https://example.com/file", destination, max_bytes=10)
    assert not destination.exists() and not destination.with_suffix(".part").exists()


def test_ai_rights_confirmation_is_required_before_billing(cfg, store, monkeypatch):
    cfg.ai["enabled"] = True
    with pytest.raises(ValueError, match="rights"):
        generate_video(cfg, store, None, NOW)
    assert not store.data["ai_requests"]


def test_source_mutation_after_review_is_detected(cfg, store, tmp_path):
    source = store.path / "media/reviewed.jpg"
    Image.new("RGB", (100, 100), "red").save(source)
    asset = insert(store, kind="image", digest="wrong-review-hash")
    asset["state_path"] = "media/reviewed.jpg"
    with pytest.raises(ValueError, match="Source changed"):
        prepare(cfg, store, None, asset, "feed", tmp_path)


def test_api_error_keeps_numeric_codes_and_redacts_response_body():
    from naiwa_bot.network import checked_json, RemoteError
    response = httpx.Response(400, json={"error":{"code":100, "error_subcode":33, "message":"unsafe secret-token"}})
    with pytest.raises(RemoteError) as error:
        checked_json(response)
    assert "code=100" in str(error.value) and "secret-token" not in str(error.value)
