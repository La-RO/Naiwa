from datetime import date, datetime, timedelta
import time

from .catalogue import eligible, import_catalogue, publishable
from .auto_video import replenish_from_web
from .media import MEDIA_POLICY_VERSION, prepare
from .providers import Instagram, discover, generate_video
from .network import RemoteError
from .video_gen import generation_outcome, pending_generation


TERMINAL = {"published", "needs_review", "abandoned"}


def due_slots(config, state, now):
    local = now.astimezone(config.timezone)
    day = local.date()
    anchor = date.fromisoformat(config.schedule["start_date"] or state["start_date"] or day.isoformat())
    if day < anchor:
        return []
    slots = []
    if local.hour >= config.schedule["story_hour"]:
        slots.append(("story:" + day.isoformat(), "story"))
    if local.hour >= config.schedule["feed_hour"] and (day - anchor).days % config.schedule["feed_every_days"] == 0:
        slots.append(("feed:" + day.isoformat(), "feed"))
    return [(slot, channel) for slot, channel in slots if state["jobs"].get(slot, {}).get("status") not in TERMINAL]


def preview(config, store, now):
    output = []
    # Simulate reservations in a copy so the same video is not promised twice.
    import copy
    simulated = copy.copy(store)
    simulated.data = copy.deepcopy(store.data)
    for slot, channel in due_slots(config, simulated.data, now):
        existing = simulated.data["jobs"].get(slot, {})
        choices = eligible(simulated, channel, now, config.schedule["reuse_after_days"])
        chosen = existing.get("asset_id") or (choices[0]["id"] if choices else None)
        output.append({"slot": slot, "asset_id": chosen, "status": existing.get("status", "available" if chosen else "no_approved_material")})
        if chosen and not existing:
            simulated.data["jobs"][slot] = {"status": "planned", "asset_id": chosen, "channel": channel}
    return output


def check_duplicate(store, slot, digest, now, days):
    cutoff = now - timedelta(days=days)
    for other_slot, other in store.data["jobs"].items():
        if other_slot == slot or other.get("sha256") != digest or other["status"] == "blocked" or (other["status"] == "abandoned" and not other.get("uncertain_publish")):
            continue
        if other["status"] != "published" or datetime.fromisoformat(other["published_at"]) > cutoff:
            raise ValueError("Duplicate content is already reserved or was recently published")


def publicly_ready(client, url, sleeper=time.sleep):
    for attempt in range(5):
        with client.stream("GET", url, follow_redirects=True, timeout=60) as response:
            if response.status_code == 200:
                return
        if attempt < 4:
            sleeper(3)
    raise ValueError("Prepared media is not publicly accessible; check repository visibility")


def publish_slot(config, store, client, ig, slot, channel, now, scratch, preparer=prepare, preflight=publicly_ready):
    job = store.data["jobs"].get(slot)
    if job and job["status"] in TERMINAL:
        return job["status"]
    if job and job["status"] == "publishing":
        job.update(status="needs_review", error="Run interrupted during publish; verify Instagram before reconciling")
        store.save()
        return "needs_review"
    if job and job.get("asset_id"):
        reserved = store.data["assets"].get(job["asset_id"], {})
        invalid = (not publishable(reserved) or (channel == "story" and reserved.get("kind") != "video")
                   or job.get("kind") != reserved.get("kind"))
        if invalid:
            job.update(status="blocked", error="Media no longer matches current content rules")
            store.save()
        elif job.get("media_policy_version") != MEDIA_POLICY_VERSION:
            for field in ("prepared_path", "media_url", "container_id", "sha256"):
                job.pop(field, None)
            job.update(status="planned", attempts=0, media_policy_version=MEDIA_POLICY_VERSION)
            store.save()
    if not job or job["status"] in ("blocked", "generating"):
        choices = eligible(store, channel, now, config.schedule["reuse_after_days"])
        web_status = "not_attempted"
        generation_status, generation_reason = "not_attempted", ""
        pending = pending_generation(store) if channel == "story" else None
        if not choices and pending:
            web_status = "generation_pending"
        elif not choices and channel == "story" and config.discovery.get("auto_publish", False):
            web = replenish_from_web(config, store, client, now, scratch / "discovery")
            web_status = web["status"]
            choices = eligible(store, channel, now, config.schedule["reuse_after_days"])
        if not choices and channel == "story" and (web_status == "no_usable_video" or pending):
            try:
                generate_video(config, store, client, now)
                generation_status, generation_reason = generation_outcome(config, store, now)
            except (ValueError, RemoteError) as error:
                generation_status, _ = generation_outcome(config, store, now)
                if generation_status == "daily_limit":
                    generation_status = "unavailable"
                generation_reason = safe_error(error)
            choices = eligible(store, channel, now, config.schedule["reuse_after_days"])
        if not choices:
            waiting = generation_status in ("submitted", "pending", "poll_failed", "download_failed")
            store.data["jobs"][slot] = {"channel": channel, "status": "generating" if waiting else "blocked",
                "error": "No usable unused material; web status: " + web_status}
            if generation_status != "not_attempted":
                store.data["jobs"][slot].update(generation_status=generation_status, generation_reason=generation_reason)
            store.save()
            return "waiting" if waiting else "blocked"
        asset = choices[0]
        job = {"channel": channel, "status": "planned", "asset_id": asset["id"], "kind": asset["kind"],
               "attempts": 0, "created_at": now.isoformat(), "media_policy_version": MEDIA_POLICY_VERSION}
        store.data["jobs"][slot] = job
        store.save()
    asset = store.data["assets"][job["asset_id"]]
    if not publishable(asset):
        job.update(status="blocked", error="Asset is excluded by current content or rights rules")
        store.save()
        return "blocked"
    if job["attempts"] >= 3:
        return "failed"
    try:
        job["attempts"] += 1
        if not job.get("prepared_path"):
            job["status"] = "preparing"
            store.save()
            path, digest = preparer(config, store, client, asset, channel, scratch)
            check_duplicate(store, slot, digest, now, config.schedule["reuse_after_days"])
            job.update(prepared_path=path, sha256=digest, status="ready")
            store.save()  # Media must reach the public branch BEFORE creating a container.
        if not job.get("media_url"):
            job["media_url"] = store.public_url(job["prepared_path"])
        if not job.get("container_id"):
            preflight(client, job["media_url"])
            job["status"] = "creating"
            store.save()
            job["container_id"] = str(ig.create(job, asset, job["media_url"]))
            job["status"] = "waiting"
            store.save()
        status = ig.status(job["container_id"])
        if status == "IN_PROGRESS":
            # Polling is not a failed attempt; next hourly run continues this container.
            job["attempts"] -= 1
            job["status"] = "waiting"
            store.save()
            return "waiting"
        if status == "PUBLISHED":
            job.update(status="needs_review", error="Container is published but media ID is missing; reconcile manually")
            store.save()
            return "needs_review"
        if status in ("ERROR", "EXPIRED"):
            job.pop("container_id", None)
            raise ValueError("Instagram container failed or expired")
        if status != "FINISHED":
            raise ValueError("Instagram container returned an unexpected state")
        job["status"] = "publishing"
        store.save()  # Durable intent before the irreversible API call.
    except Exception as error:
        job.update(status="failed", error=safe_error(error))
        store.save()
        return "failed"
    try:
        media_id = str(ig.publish(job["container_id"]))
    except Exception:
        job.update(status="needs_review", error="Publish result is unknown; inspect Instagram, then reconcile or abandon")
        store.save()
        return "needs_review"
    job.update(status="published", media_id=media_id, published_at=now.isoformat(), error="")
    store.save()
    return "published"


def safe_error(error):
    # Only our own ValueError messages are suitable for a public journal.
    return str(error)[:200] if type(error) in (ValueError, RemoteError) else type(error).__name__ + ": operation failed; check configuration/network"


def run(config, store, client, now, scratch, ig_factory=Instagram):
    if store.data["paused"]:
        return {"paused": True}
    import_catalogue(store, config.root)
    ig = ig_factory(config, store, client)
    ig.verify(now)
    results = {}
    local = now.astimezone(config.timezone)
    has_story_stock = bool(eligible(store, "story", now, config.schedule["reuse_after_days"]))
    if (config.discovery["enabled"] and local.hour >= config.discovery["hour"]
            and (not config.discovery.get("only_when_story_empty", False) or not has_story_stock)):
        try:
            results["discovery"] = discover(config, store, client, now)
        except Exception as error:
            results["discovery_error"] = safe_error(error)
    # Detect interrupted publishes on older days too; never backfill missed slots.
    for job in store.data["jobs"].values():
        if job["status"] == "publishing":
            job.update(status="needs_review", error="Run interrupted during publish; inspect Instagram")
            store.save()
    for slot, channel in due_slots(config, store.data, now):
        try:
            results[slot] = publish_slot(config, store, client, ig, slot, channel, now, scratch / channel)
        except Exception as error:
            results[slot] = safe_error(error)
    return results
