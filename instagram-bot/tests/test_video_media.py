import hashlib
from pathlib import Path
import subprocess

import imageio_ffmpeg
from PIL import Image
import pytest

from naiwa_bot.config import Config
from naiwa_bot.media import MEDIA_POLICY_VERSION, prepare, validate_web_video
from naiwa_bot.state import Store


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cfg():
    result = Config.load(ROOT)
    result.ai["duration_seconds"] = 5
    return result


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "state")


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    folder = tmp_path_factory.mktemp("motion-policy-media")
    generated = {}
    for name, source, duration in (("motion", "testsrc2=size=160x160:rate=15", 3.2),
                                   ("long_motion", "testsrc2=size=160x160:rate=15", 8),
                                   ("still", "color=c=yellow:s=160x160:r=15", 3.2),
                                   ("too_short", "testsrc2=size=160x160:rate=15", 1.5)):
        path = folder / (name + ".mp4")
        result = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", source, "-t", str(duration), "-an", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(path)], capture_output=True, timeout=30)
        assert result.returncode == 0, "Local fixture generation failed"
        generated[name] = path
    jpeg = folder / "image.jpg"
    Image.new("RGB", (160, 160), "yellow").save(jpeg, "JPEG")
    generated["jpeg"] = jpeg
    return generated


def asset_for(store, source, kind="video", **updates):
    name = "source.mp4" if kind == "video" else "source.jpg"
    state_path = "media/" + name
    target = store.path / state_path
    target.write_bytes(source.read_bytes())
    asset = {"id": "test", "kind": kind, "title": "Naiwa daily life", "state_path": state_path,
        "local_path": "", "url": "", "source_url": "https://public.test/original", "credit": "Naiwa Club",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "ai_generated": False}
    asset.update(updates)
    return asset


def cache_path(store, asset, channel, limit):
    key = hashlib.sha256(f"v{MEDIA_POLICY_VERSION}:{asset['sha256']}:{channel}:{asset['credit']}:{asset['ai_generated']}:{limit}".encode()).hexdigest()
    return store.path / "media" / (key + ".mp4")


def test_dynamic_video_validation_returns_duration(clips):
    duration = validate_web_video(clips["motion"])
    assert 3 <= duration <= 3.5


def test_frozen_color_video_is_not_motion(clips):
    with pytest.raises(ValueError, match="no visible motion"):
        validate_web_video(clips["still"])


def test_jpeg_cannot_masquerade_as_mp4(clips, tmp_path):
    source = tmp_path / "pretend.mp4"
    source.write_bytes(clips["jpeg"].read_bytes())
    with pytest.raises(ValueError, match="not an MP4"):
        validate_web_video(source)


def test_duration_and_download_size_limits_remain(clips, tmp_path):
    with pytest.raises(ValueError, match="3..600"):
        validate_web_video(clips["too_short"])
    too_large = tmp_path / "oversize.mp4"
    with too_large.open("wb") as output:
        output.seek(80_000_000)
        output.write(b"x")
    with pytest.raises(ValueError, match="80 MB"):
        validate_web_video(too_large)


def test_image_story_is_rejected_before_creating_video(cfg, store, clips, tmp_path):
    asset = asset_for(store, clips["jpeg"], kind="image")
    with pytest.raises(ValueError, match="image feed Posts"):
        prepare(cfg, store, None, asset, "story", tmp_path / "scratch")
    assert not list((store.path / "media").glob("*.mp4"))


def test_image_feed_remains_a_jpeg_post(cfg, store, clips, tmp_path):
    asset = asset_for(store, clips["jpeg"], kind="image")
    relative, digest = prepare(cfg, store, None, asset, "feed", tmp_path / "scratch")
    assert relative.endswith(".jpg") and digest == asset["sha256"]
    with Image.open(store.path / relative) as result:
        assert result.format == "JPEG" and result.size == (1080, 1350)
    assert not list((store.path / "media").glob("*.mp4"))


def test_motion_source_produces_motion_story_mp4(cfg, store, clips, tmp_path):
    asset = asset_for(store, clips["motion"])
    relative, digest = prepare(cfg, store, None, asset, "story", tmp_path / "scratch")
    assert relative.endswith(".mp4") and digest == asset["sha256"]
    output = store.path / relative
    assert 3 <= validate_web_video(output) <= 3.5
    # The same policy can reuse an existing output after checking its source.
    before = output.stat().st_mtime_ns
    assert prepare(cfg, store, None, asset, "story", tmp_path / "scratch") == (relative, digest)
    assert output.stat().st_mtime_ns == before


@pytest.mark.parametrize("style", ["slideshow", "still", "pan_zoom"])
def test_declared_slideshow_styles_rejected_even_with_cached_video(cfg, store, clips, tmp_path, style):
    asset = asset_for(store, clips["motion"], video_style=style)
    cache_path(store, asset, "story", 15).write_bytes(clips["motion"].read_bytes())
    with pytest.raises(ValueError, match="Slideshows"):
        prepare(cfg, store, None, asset, "story", tmp_path / "scratch")


@pytest.mark.parametrize("bad_source, message", [("jpeg", "not an MP4"), ("still", "no visible motion")])
def test_cached_target_cannot_bypass_source_validation(cfg, store, clips, tmp_path, bad_source, message):
    asset = asset_for(store, clips[bad_source])
    cache_path(store, asset, "story", 15).write_bytes(clips["motion"].read_bytes())
    with pytest.raises(ValueError, match=message):
        prepare(cfg, store, None, asset, "story", tmp_path / "scratch")


def test_ai_duration_default_and_changed_limit_invalidate_old_cache(cfg, store, clips, tmp_path):
    asset = asset_for(store, clips["long_motion"], ai_generated=True)
    cfg.ai.pop("duration_seconds", None)
    # Simulate a pre-policy eight-second cache entry. It must not be selected.
    old_key = hashlib.sha256(f"{asset['sha256']}:story:{asset['credit']}:True".encode()).hexdigest()
    old_cache = store.path / "media" / (old_key + ".mp4")
    old_cache.write_bytes(clips["long_motion"].read_bytes())
    relative5, _ = prepare(cfg, store, None, asset, "story", tmp_path / "scratch5")
    assert (store.path / relative5) != old_cache
    assert 3 <= validate_web_video(store.path / relative5) <= 5
    cfg.ai["duration_seconds"] = 3
    relative3, _ = prepare(cfg, store, None, asset, "story", tmp_path / "scratch3")
    assert relative3 != relative5
    assert 3 <= validate_web_video(store.path / relative3) <= 3.1
    assert MEDIA_POLICY_VERSION == 2


@pytest.mark.parametrize("duration", [2, 6, True, "5"])
def test_ai_duration_limits_are_checked_before_preparation(cfg, store, clips, tmp_path, duration):
    cfg.ai["duration_seconds"] = duration
    asset = asset_for(store, clips["motion"], ai_generated=True)
    with pytest.raises(ValueError, match="between 3 and 5"):
        prepare(cfg, store, None, asset, "story", tmp_path / "scratch")
