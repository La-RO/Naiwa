import hashlib
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import inside
from .network import download


MEDIA_POLICY_VERSION = 2


def font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"):
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def overlay(size, asset):
    width, height = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    credit = asset["credit"]
    if not credit.isascii():
        credit = urlparse(asset["source_url"]).hostname or "Naiwa Club"
    lines = ["NAIWA CLUB", "Credit: " + credit[:55]]
    if asset["ai_generated"]:
        lines.insert(1, "AI-GENERATED / FICTIONAL DAILY LIFE")
    top = height - 180 - len(lines) * 42 if height > 1500 else height - 50 - len(lines) * 42
    draw.rectangle((0, top - 20, width, top + len(lines) * 42 + 15), fill=(0, 0, 0, 175))
    for index, line in enumerate(lines):
        draw.text((42, top + index * 42), line, fill="white", font=font(28))
    return layer


def validate_web_video(source):
    """Validate MP4 frames and reject a static first-five-second sample.

    Thumbnail changes establish that a sample is not frozen. They do not
    distinguish every slideshow, camera pan, or animation from genuine footage.
    """
    if not source.stat().st_size or source.stat().st_size > 80_000_000:
        raise ValueError("Web video is empty or exceeds 80 MB")
    with source.open("rb") as stream:
        if stream.read(12)[4:8] != b"ftyp":
            raise ValueError("Web video is not an MP4 file")
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    input_limits = ["-protocol_whitelist", "file,pipe", "-max_pixels", "40000000", "-threads", "2"]
    probe = subprocess.run([ffmpeg, "-hide_banner", "-max_alloc", "268435456", *input_limits,
                            "-format_whitelist", "mov", "-i", str(source)], capture_output=True, timeout=30)
    match = re.search(rb"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
    duration = sum(float(value) * multiplier for value, multiplier in zip(match.groups(), (3600, 60, 1))) if match else 0
    if not 3 <= duration <= 600 or b"Video:" not in probe.stderr:
        raise ValueError("Web video must contain a readable 3..600 second video stream")
    decoded = subprocess.run([ffmpeg, "-v", "error", "-xerror", "-max_alloc", "268435456", *input_limits,
                              "-format_whitelist", "mov", "-i", str(source),
                              "-t", "60", "-map", "0:v:0", "-f", "null", "-"], capture_output=True, timeout=180)
    if decoded.returncode:
        raise ValueError("Web video frames could not be decoded")
    sampled = subprocess.run([ffmpeg, "-v", "error", "-xerror", "-max_alloc", "268435456", *input_limits,
                              "-format_whitelist", "mov", "-i", str(source), "-t", "5", "-map", "0:v:0",
                              "-vf", "fps=2,scale=64:64:force_original_aspect_ratio=decrease,pad=64:64:(ow-iw)/2:(oh-ih)/2,format=gray",
                              "-an", "-threads", "1", "-f", "rawvideo", "pipe:1"],
                             capture_output=True, timeout=60)
    frame_size = 64 * 64
    if sampled.returncode or len(sampled.stdout) < frame_size * 2 or len(sampled.stdout) % frame_size:
        raise ValueError("Web video motion sample could not be decoded")
    frames = [sampled.stdout[index:index + frame_size] for index in range(0, len(sampled.stdout), frame_size)]
    # Ignore tiny codec fluctuations; one changing frame is enough for this
    # deliberately limited static-frame check.
    if not any(sum(abs(a - b) for a, b in zip(frames[0], frame)) > frame_size / 2 for frame in frames[1:]):
        raise ValueError("Video contains no visible motion in the first five seconds; still images are not videos")
    return duration


def prepare(config, store, client, asset, channel, scratch):
    if asset["kind"] == "image" and channel != "feed":
        raise ValueError("Images may only be published as image feed Posts")
    if asset["kind"] == "video" and asset.get("video_style") in ("slideshow", "still", "pan_zoom"):
        raise ValueError("Slideshows and still-image animations cannot be published as videos")
    ai_limit = config.ai.get("duration_seconds", 5)
    if asset["ai_generated"] and (type(ai_limit) not in (int, float) or not 3 <= ai_limit <= 5):
        raise ValueError("AI video duration must be between 3 and 5 seconds")
    scratch.mkdir(parents=True, exist_ok=True)
    if asset.get("state_path"):
        source = inside(store.path, asset["state_path"])
    elif asset.get("local_path"):
        source = inside(config.root, asset["local_path"])
    else:
        source = scratch / ("input.mp4" if asset["kind"] == "video" else "input.image")
        download(client, asset["url"], source)
    # Source validation precedes every cache lookup. A stale prepared file must
    # never turn a JPEG, frozen clip, or rejected source into an accepted video.
    duration = validate_web_video(source) if asset["kind"] == "video" else None
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if asset.get("sha256") and asset["sha256"] != digest:
        raise ValueError("Source changed after import/review; import as a new asset and review again")
    asset["sha256"] = digest
    limit = ai_limit if asset["ai_generated"] else (15 if channel == "story" else 60)
    key = hashlib.sha256(f"v{MEDIA_POLICY_VERSION}:{digest}:{channel}:{asset['credit']}:{asset['ai_generated']}:{limit}".encode()).hexdigest()
    suffix = ".mp4" if asset["kind"] == "video" else ".jpg"
    relative = "media/" + key + suffix
    target = store.path / relative
    if not target.exists():
        if asset["kind"] == "image":
            size = (1080, 1350)
            with Image.open(source) as image:
                if image.width * image.height > 40_000_000:
                    raise ValueError("Image exceeds pixel limit")
                converted = ImageOps.exif_transpose(image).convert("RGB")
                canvas = ImageOps.pad(converted, size, color="#fff9df", method=Image.Resampling.LANCZOS)
                canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay(size, asset)).convert("RGB")
                canvas.save(target, "JPEG", quality=92, optimize=True)
        else:
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            input_limits = ["-protocol_whitelist", "file,pipe", "-max_pixels", "40000000", "-threads", "2"]
            input_limits += ["-format_whitelist", "mov"]
            stamp = scratch / "overlay.png"
            overlay((1080, 1920), asset).save(stamp)
            temporary = target.with_suffix(".tmp.mp4")
            filters = "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0xfff9df,setsar=1[v];[v][1:v]overlay=0:0[out]"
            command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-max_alloc", "268435456",
                *input_limits, "-i", str(source), "-i", str(stamp),
                "-filter_complex", filters, "-map", "[out]", "-map", "0:a?", "-t", str(min(duration, limit)),
                "-r", "30", "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(temporary)]
            result = subprocess.run(command, capture_output=True, timeout=480)
            if result.returncode:
                temporary.unlink(missing_ok=True)
                raise ValueError("Video normalization failed; source may not be supported")
            temporary.replace(target)
    if not target.stat().st_size or target.stat().st_size > 80_000_000:
        raise ValueError("Prepared media is empty or exceeds 80 MB")
    return relative, digest
