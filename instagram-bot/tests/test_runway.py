import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import httpx
import imageio_ffmpeg
import pytest

from naiwa_bot.config import Config
from naiwa_bot.engine import publish_slot
from naiwa_bot.network import RemoteError
from naiwa_bot.providers import generate_video
from naiwa_bot.state import Store
from naiwa_bot.video_gen import pending_generation


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 24, 8, 30, tzinfo=timezone.utc)
DAY = "2026-10-24"
TASK = "17f20503-6c24-4c16-946b-35dbbce2af2f"
OUTPUT = "https://cdn.public.test/video.mp4?signature=private-transient-link"


class Journal(Store):
    def __init__(self, path):
        super().__init__(path)
        self.snapshots = []
        self.fail_on = None

    def save(self):
        if self.fail_on == len(self.snapshots) + 1:
            raise RuntimeError("Simulated durable-state failure")
        super().save()
        self.snapshots.append(copy.deepcopy(self.data))

    def public_url(self, path):
        return "https://public.test/" + path


@pytest.fixture
def cfg(monkeypatch):
    cfg = Config.load(ROOT)
    cfg.ai.update(enabled=True, provider="runway", model="gen4_turbo", duration_seconds=5,
                  character_rights_confirmed=True, auto_approve=True, max_requests_per_day=1)
    monkeypatch.setenv("RUNWAYML_API_SECRET", "dummy-runway-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-unused-gemini-key")
    monkeypatch.setattr("naiwa_bot.network.validate_public_url", lambda _: None)
    return cfg


@pytest.fixture
def store(tmp_path):
    return Journal(tmp_path / "state")


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    folder = tmp_path_factory.mktemp("runway-video")
    result = {}
    for name, source, seconds in [("motion", "testsrc2=size=96x96:rate=12", 5),
                                   ("still", "color=c=yellow:size=96x96:rate=12", 5),
                                   ("long", "testsrc2=size=96x96:rate=12", 10)]:
        target = folder / (name + ".mp4")
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
                        "-f", "lavfi", "-i", source, "-t", str(seconds), "-c:v", "libx264",
                        "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)],
                       check=True, capture_output=True, timeout=30)
        result[name] = target.read_bytes()
    return result


def recorded(store):
    return store.data["ai_requests"][DAY][0]


def transport(store, clips, calls, *, status="SUCCEEDED", content="motion"):
    def handler(request):
        calls.append(request)
        if request.method == "POST":
            assert store.snapshots[-1]["ai_requests"][DAY][0]["status"] == "requested"
            return httpx.Response(200, json={"id": TASK})
        if request.url.host == "api.dev.runwayml.com":
            assert request.url.path == "/v1/tasks/" + TASK
            assert store.snapshots[-1]["ai_requests"][DAY][0]["task_id"] == TASK
            return httpx.Response(200, json={"id": TASK, "status": status, "output": [OUTPUT]})
        assert request.url.host == "cdn.public.test"
        assert "authorization" not in request.headers and "cookie" not in request.headers
        return httpx.Response(200, content=clips[content])
    return httpx.MockTransport(handler)


def test_runway_five_seconds_actual_motion_enters_pool(cfg, store, clips):
    calls = []
    with httpx.Client(transport=transport(store, clips, calls)) as client:
        asset = generate_video(cfg, store, client, NOW)
        assert generate_video(cfg, store, client, NOW + timedelta(minutes=2)) is None
    assert [r.method for r in calls] == ["POST", "GET", "GET"]
    body = json.loads(calls[0].content)
    assert body["model"] == "gen4_turbo" and body["duration"] == 5 and body["ratio"] == "720:1280"
    assert body["promptImage"].startswith("data:image/webp;base64,")
    assert "Visible body motion" in body["promptText"] and "image pan/zoom" in body["promptText"]
    assert calls[0].headers["authorization"] == "Bearer dummy-runway-secret"
    assert calls[0].headers["x-runway-version"] == "2024-11-06"
    assert recorded(store)["status"] == "completed" and asset["provider_task_id"] == TASK
    assert asset["rights"] == "ai" and asset["reviewed"] and asset["video_style"] == "motion"
    assert (store.path / asset["state_path"]).read_bytes() == clips["motion"]
    serialized = json.dumps(store.data)
    assert "dummy-runway-secret" not in serialized and "signature=" not in serialized
    assert not list(store.path.glob("*.pending"))


def test_pending_task_resumes_after_process_restart_without_second_charge(cfg, store, clips):
    calls = []
    with httpx.Client(transport=transport(store, clips, calls, status="RUNNING")) as client:
        assert generate_video(cfg, store, client, NOW) is None
        assert generate_video(cfg, store, client, NOW) is None  # five-second polling floor
    restored = Journal(store.path)
    with httpx.Client(transport=transport(restored, clips, calls)) as client:
        asset = generate_video(cfg, restored, client, NOW + timedelta(hours=1))
    assert asset and sum(r.method == "POST" for r in calls) == 1
    assert pending_generation(restored) is None


def test_pending_yesterday_is_retrieved_before_new_day_quota(cfg, store, clips):
    calls = []
    with httpx.Client(transport=transport(store, clips, calls, status="PENDING")) as client:
        assert generate_video(cfg, store, client, NOW) is None
    with httpx.Client(transport=transport(store, clips, calls)) as client:
        assert generate_video(cfg, store, client, NOW + timedelta(days=1))
    assert sum(r.method == "POST" for r in calls) == 1
    assert list(store.data["ai_requests"]) == [DAY]


@pytest.mark.parametrize("failure", ["timeout", "http_error", "invalid_id"])
def test_uncertain_submission_consumes_quota_and_never_reposts(cfg, store, failure):
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("secret details must not be exposed")
        if failure == "http_error":
            return httpx.Response(503, json={"error": "secret internal details"})
        return httpx.Response(200, json={"id": "../invalid-task"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RemoteError):
            generate_video(cfg, store, client, NOW)
        assert generate_video(cfg, store, client, NOW + timedelta(hours=1)) is None
    assert len(calls) == 1 and recorded(store)["status"] == "failed_or_unknown"
    assert not store.data["assets"]


@pytest.mark.parametrize("status", ["FAILED", "CANCELLED"])
def test_provider_failure_never_submits_again_same_day(cfg, store, clips, status):
    calls = []
    with httpx.Client(transport=transport(store, clips, calls, status=status)) as client:
        assert generate_video(cfg, store, client, NOW) is None
        assert generate_video(cfg, store, client, NOW + timedelta(hours=1)) is None
    assert recorded(store)["status"] == "failed" and len(calls) == 2


@pytest.mark.parametrize("bad", ["still", "long", "corrupt", "duplicate"])
def test_invalid_outputs_are_not_saved_or_rebilled(cfg, store, clips, bad):
    clips = dict(clips, corrupt=b"not-an-mp4")
    if bad == "duplicate":
        store.data["assets"]["existing"] = {"sha256": hashlib.sha256(clips["motion"]).hexdigest()}
    before = copy.deepcopy(store.data["assets"])
    calls = []
    with httpx.Client(transport=transport(store, clips, calls, content="motion" if bad == "duplicate" else bad)) as client:
        with pytest.raises(RemoteError):
            generate_video(cfg, store, client, NOW)
        assert generate_video(cfg, store, client, NOW + timedelta(hours=1)) is None
    assert recorded(store)["status"] == "invalid_output"
    assert store.data["assets"] == before and len(calls) == 3
    assert not list((store.path / "media").iterdir())
    assert not list(store.path.glob("*.pending")) and not list(store.path.glob("*.part"))


def test_state_failure_before_submission_prevents_any_paid_request(cfg, store):
    store.fail_on = 1
    with pytest.raises(RuntimeError, match="durable-state"):
        generate_video(cfg, store, None, NOW)


def test_state_failure_after_submission_never_causes_a_second_post(cfg, store):
    store.fail_on = 2
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": TASK})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError):
            generate_video(cfg, store, client, NOW)
    restored = Journal(store.path)  # durable record is requested, with no task ID
    assert generate_video(cfg, restored, None, NOW + timedelta(hours=1)) is None
    assert len(calls) == 1


def test_poll_timeout_resumes_saved_task_without_new_generation(cfg, store, clips):
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"id": TASK})
        raise httpx.ReadTimeout("temporary")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RemoteError):
            generate_video(cfg, store, client, NOW)
    assert recorded(store)["status"] == "poll_failed"
    with httpx.Client(transport=transport(store, clips, calls)) as client:
        assert generate_video(cfg, store, client, NOW + timedelta(hours=1))
    assert sum(r.method == "POST" for r in calls) == 1


def test_generated_material_can_still_require_review(cfg, store, clips):
    cfg.ai["auto_approve"] = False
    with httpx.Client(transport=transport(store, clips, [])) as client:
        asset = generate_video(cfg, store, client, NOW)
    assert asset["rights"] == "pending" and not asset["reviewed"]


@pytest.mark.parametrize("provider", ["gemini", "openai", "deepseek"])
def test_legacy_provider_settings_never_call_other_services(cfg, store, provider):
    cfg.ai["provider"] = provider
    with pytest.raises(ValueError, match="other providers are not called"):
        generate_video(cfg, store, None, NOW)
    assert not store.data["ai_requests"]


def test_missing_key_blocks_only_story_and_image_post_can_publish(cfg, store, tmp_path, monkeypatch):
    monkeypatch.delenv("RUNWAYML_API_SECRET")
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", lambda *_: {"status": "no_usable_video"})
    image = {"id": "photo", "kind": "image", "title": "Naiwa", "rights": "permission", "reviewed": True,
             "credit": "Club", "evidence": "Operator permission", "added_at": NOW.isoformat(),
             "ai_generated": False, "source_url": "https://public.test/source", "sha256": "a" * 64}
    store.data["assets"]["photo"] = image
    class IG:
        def create(self, job, asset, url):
            assert job["channel"] == "feed" and asset["kind"] == "image"
            return "container"
        def status(self, _):
            return "FINISHED"
        def publish(self, _):
            return "media"
    def process(slot, channel):
        return publish_slot(cfg, store, None, IG(), slot, channel, NOW, tmp_path,
                            preparer=lambda *_: ("media/test.jpg", "a" * 64), preflight=lambda *_: None)
    assert process("story:" + DAY, "story") == "blocked"
    assert "RUNWAYML_API_SECRET" in store.data["jobs"]["story:" + DAY]["generation_reason"]
    assert process("feed:" + DAY, "feed") == "published"
    assert not store.data["ai_requests"]


def test_pending_story_resumes_without_repeating_search_or_submission(cfg, store, clips, tmp_path, monkeypatch):
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", lambda *_: {"status": "no_usable_video"})
    class IG:
        creates = 0
        publishes = 0
        def create(self, *_):
            self.creates += 1
            return "container"
        def status(self, _):
            return "FINISHED"
        def publish(self, _):
            self.publishes += 1
            return "1234"
    ig = IG()
    calls = []
    def process(client, now):
        return publish_slot(cfg, store, client, ig, "story:" + DAY, "story", now, tmp_path,
                            preparer=lambda *args: (args[3]["state_path"], args[3]["sha256"]),
                            preflight=lambda *_: None)
    with httpx.Client(transport=transport(store, clips, calls, status="RUNNING")) as client:
        assert process(client, NOW) == "waiting"
    assert store.data["jobs"]["story:" + DAY]["status"] == "generating"
    assert ig.publishes == 0
    def no_search(*_):
        pytest.fail("Existing paid task should be resumed even if search is unavailable")
    monkeypatch.setattr("naiwa_bot.engine.replenish_from_web", no_search)
    with httpx.Client(transport=transport(store, clips, calls)) as client:
        assert process(client, NOW + timedelta(hours=1)) == "published"
        assert process(client, NOW + timedelta(hours=2)) == "published"
    assert ig.creates == ig.publishes == 1
    assert sum(r.method == "POST" for r in calls) == 1


def test_temporary_download_failure_retries_same_task_without_new_charge(cfg, store, clips):
    calls = []
    success = transport(store, clips, calls)
    def first(request):
        if request.url.host == "cdn.public.test":
            calls.append(request)
            return httpx.Response(503)
        return success.handle_request(request)
    with httpx.Client(transport=httpx.MockTransport(first)) as client:
        with pytest.raises(RemoteError):
            generate_video(cfg, store, client, NOW)
    assert recorded(store)["status"] == "download_failed"
    assert not list(store.path.glob("*.pending"))
    with httpx.Client(transport=transport(store, clips, calls)) as client:
        assert generate_video(cfg, store, client, NOW + timedelta(hours=1))
    assert sum(r.method == "POST" for r in calls) == 1


def test_missing_provider_task_releases_pending_status_without_rebilling(cfg, store):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"id": TASK}) if request.method == "POST" else httpx.Response(404)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert generate_video(cfg, store, client, NOW) is None
        assert generate_video(cfg, store, client, NOW + timedelta(hours=1)) is None
    assert recorded(store)["status"] == "failed" and not pending_generation(store)
    assert len(calls) == 2
