"""Durable, on-demand Runway video generation; no SDK auto-retries."""
import base64
from datetime import datetime, timedelta
import hashlib
import os
import re

from PIL import Image

from .catalogue import asset_id
from .config import inside
from .media import validate_web_video
from .network import RemoteError, checked_json, download


BASE = "https://api.dev.runwayml.com/v1"
ACTIVE = {"submitted", "pending", "poll_failed", "download_failed"}
TASK_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}")


def pending_generation(store):
    for day in sorted(store.data["ai_requests"]):
        for record in store.data["ai_requests"][day]:
            if record.get("provider") == "runway" and record.get("task_id") and record["status"] in ACTIVE:
                return record
    return None


def generation_outcome(config, store, now):
    if not config.ai["enabled"]:
        return "disabled", "AI video generation is disabled"
    day = now.astimezone(config.timezone).date().isoformat()
    records = store.data["ai_requests"].get(day, [])
    record = pending_generation(store) or (records[-1] if records else None)
    if record:
        messages = {"completed": "Generated video awaits review or is already reserved/used",
                    "pending": "Runway video is generating; next hourly run will check the same task",
                    "submitted": "Runway task saved; next run will check its status"}
        return record["status"], record.get("error") or messages.get(record["status"], "Daily generation request is already reserved")
    return "daily_limit", "Daily generation request limit reached"


def _request(client, method, path, headers, allow_missing=False, **kwargs):
    response = client.request(method, BASE + path, headers=headers, follow_redirects=False, timeout=60, **kwargs)
    if allow_missing and response.status_code == 404:
        return None
    return checked_json(response)


def generate_video(config, store, client, now):
    settings = config.ai
    if not settings["enabled"]:
        return None
    if settings.get("provider") != "runway" or settings["model"] != "gen4_turbo":
        raise ValueError("Configure ai.provider=runway and ai.model=gen4_turbo; other providers are not called")
    if not settings["character_rights_confirmed"]:
        raise ValueError("Confirm character/reference rights before AI generation")
    api_key = os.environ.get("RUNWAYML_API_SECRET", "")
    if not api_key:
        raise ValueError("Set RUNWAYML_API_SECRET in GitHub Secrets to enable Runway generation")
    headers = {"Authorization": "Bearer " + api_key, "X-Runway-Version": "2024-11-06"}
    record = pending_generation(store)
    if record is None:
        seconds = settings.get("duration_seconds", 5)
        if type(seconds) is not int or not 3 <= seconds <= 5:
            raise ValueError("AI duration_seconds must be 3..5")
        day = now.astimezone(config.timezone).date().isoformat()
        requests = store.data["ai_requests"].get(day, [])
        if len(requests) >= settings["max_requests_per_day"]:
            return None
        if sum(p.stat().st_size for p in (store.path / "media").glob("*") if p.is_file()) > 240_000_000:
            raise ValueError("Not enough media storage for another generated video")
        if not settings["reference_image"]:
            raise ValueError("Set a licensed reference_image to preserve Naiwa's appearance")
        reference = inside(config.root, settings["reference_image"])
        if reference.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp") or reference.stat().st_size > 3_500_000:
            raise ValueError("Runway reference must be a JPEG/PNG/WebP image under 3.5 MB")
        with Image.open(reference) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("Runway reference image has too many pixels")
            image.verify()
        reference_bytes = reference.read_bytes()
        mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[reference.suffix.lower()]
        data_uri = "data:" + mime + ";base64," + base64.b64encode(reference_bytes).decode()
        if len(data_uri) > 5_000_000:
            raise ValueError("Encoded reference exceeds Runway's data URI limit")
        scenes = settings["daily_scenes"]
        if not scenes:
            raise ValueError("Configure at least one AI daily scene")
        scene = scenes[now.astimezone(config.timezone).date().toordinal() % len(scenes)]
        prompt = (f"Animated fictional daily life, {seconds} seconds. Preserve the mascot in the reference: "
                  f"{settings['character_description']}. The mascot is {scene}. "
                  "Visible body motion, one coherent action, warm humorous wholesome cartoon. "
                  "Locked camera, no dialogue, no text or logos. "
                  "No slideshow, frozen frames, image pan/zoom, or camera-only motion.")
        if len(prompt.encode("utf-16-le")) // 2 > 1000:
            raise ValueError("Runway prompt exceeds 1000 characters")
        identity = asset_id("ai", f"runway:{day}:{len(requests)}")
        record = {"id": identity, "provider": "runway", "status": "requested", "model": "gen4_turbo",
                  "at": now.isoformat(), "day": day, "duration_seconds": seconds, "prompt": prompt,
                  "reference_sha256": hashlib.sha256(reference_bytes).hexdigest()}
        store.data["ai_requests"].setdefault(day, []).append(record)
        store.save()  # Durable quota/intent BEFORE a potentially billable request.
        try:
            data = _request(client, "POST", "/image_to_video", headers, json={"model": "gen4_turbo",
                "promptImage": data_uri, "promptText": prompt, "ratio": "720:1280", "duration": seconds})
            task_id = data.get("id", "")
            if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
                raise ValueError("Runway returned an invalid task ID")
        except Exception:
            record.update(status="failed_or_unknown", error="Runway submission failed or is unknown; daily request retained")
            store.save()
            raise RemoteError(record["error"]) from None
        record.update(status="submitted", task_id=task_id)
        store.save()  # Resume this task after interruption; never repeat its POST.
    task_id = record["task_id"]
    if not isinstance(task_id, str) or not TASK_ID.fullmatch(task_id):
        raise ValueError("Invalid saved Runway task ID")
    if record.get("polled_at") and now - datetime.fromisoformat(record["polled_at"]) < timedelta(seconds=5):
        return None
    record["polled_at"] = now.isoformat()
    store.save()
    try:
        data = _request(client, "GET", "/tasks/" + task_id, headers, allow_missing=True)
        if data is None:
            record.update(status="failed", error="Runway task no longer exists; daily request retained")
            store.save()
            return None
        if data.get("id") != task_id:
            raise ValueError("Runway task response does not match saved task")
    except Exception:
        record.update(status="poll_failed", error="Runway status unavailable; saved task retained for the next run")
        store.save()
        raise RemoteError(record["error"]) from None
    status = data.get("status")
    if status in ("PENDING", "RUNNING", "THROTTLED"):
        record.update(status="pending", error="")
        store.save()
        return None
    if status in ("FAILED", "CANCELLED"):
        record.update(status="failed", error="Runway task failed or was cancelled; daily request retained")
        store.save()
        return None
    outputs = data.get("output")
    if status != "SUCCEEDED" or not isinstance(outputs, list) or not outputs or not isinstance(outputs[0], str):
        record.update(status="failed", error="Runway returned no completed video; daily request retained")
        store.save()
        return None
    temporary = store.path / (record["id"].split(":", 1)[1] + ".pending")
    try:
        # Signed output URLs are never persisted. Download without API credentials.
        download(client, outputs[0], temporary)
        duration = validate_web_video(temporary)
        if abs(duration - record["duration_seconds"]) > 0.3:
            raise ValueError("Generated video duration does not match the requested 3-5 seconds")
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if any(a.get("sha256") == digest for a in store.data["assets"].values()):
            raise ValueError("Generated video duplicates existing material")
    except ValueError:
        temporary.unlink(missing_ok=True)
        record.update(status="invalid_output", error="Generated video failed format, motion, duration or duplicate checks")
        store.save()
        raise RemoteError(record["error"]) from None
    except Exception:
        temporary.unlink(missing_ok=True)
        record.update(status="download_failed", error="Generated video download unavailable; saved task retained")
        store.save()
        raise RemoteError(record["error"]) from None
    path = "media/" + digest + ".mp4"
    temporary.replace(store.path / path)
    approved = settings["auto_approve"]
    asset = {"id": record["id"], "kind": "video", "title": "奶蛙虚构日常 · " + record["day"],
             "url": "", "source_url": "https://github.com/La-RO/Naiwa", "state_path": path,
             "local_path": "", "sha256": digest, "rights": "ai" if approved else "pending",
             "evidence": "Configured character rights confirmation; Runway gen4_turbo" if approved else "",
             "credit": "Naiwa Club / Runway AI", "ai_generated": True, "reviewed": approved,
             "added_at": now.isoformat(), "prompt": record["prompt"], "model": record["model"],
             "provider": "runway", "provider_task_id": task_id, "duration_seconds": record["duration_seconds"],
             "reference_sha256": record["reference_sha256"], "video_style": "motion"}
    store.data["assets"][asset["id"]] = asset
    record.update(status="completed", asset_id=asset["id"], error="")
    store.save()
    return asset
