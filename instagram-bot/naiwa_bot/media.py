import hashlib
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import inside
from .network import download


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


def prepare(config, store, client, asset, channel, scratch):
    scratch.mkdir(parents=True, exist_ok=True)
    if asset.get("state_path"):
        source = inside(store.path, asset["state_path"])
    elif asset.get("local_path"):
        source = inside(config.root, asset["local_path"])
    else:
        source = scratch / ("input.mp4" if asset["kind"] == "video" else "input.image")
        download(client, asset["url"], source)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if asset.get("sha256") and asset["sha256"] != digest:
        raise ValueError("Source changed after import/review; import as a new asset and review again")
    asset["sha256"] = digest
    key = hashlib.sha256(f"{digest}:{channel}:{asset['credit']}:{asset['ai_generated']}".encode()).hexdigest()
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
            probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(source)], capture_output=True, timeout=30)
            match = re.search(rb"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
            duration = sum(float(value) * multiplier for value, multiplier in zip(match.groups(), (3600, 60, 1))) if match else 0
            if duration < 3:
                raise ValueError("Video must have a readable duration of at least 3 seconds")
            stamp = scratch / "overlay.png"
            overlay((1080, 1920), asset).save(stamp)
            temporary = target.with_suffix(".tmp.mp4")
            filters = "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0xfff9df,setsar=1[v];[v][1:v]overlay=0:0[out]"
            command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source), "-i", str(stamp),
                "-filter_complex", filters, "-map", "[out]", "-map", "0:a?", "-t", str(min(duration, 15 if channel == "story" else 60)),
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
