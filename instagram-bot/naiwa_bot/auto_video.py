import hashlib
from urllib.parse import urlparse

from .catalogue import asset_id, eligible
from .media import validate_web_video
from .network import download
from .providers import discover
from .web_media import find_video


def replenish_from_web(config, store, client, now, scratch):
    """Find one public MP4 only when the Story pool has no usable video."""
    settings = config.discovery
    if eligible(store, "story", now, config.schedule["reuse_after_days"]):
        return {"status": "stock_available"}
    if not settings["enabled"] or not settings.get("auto_publish", False):
        return {"status": "automatic_import_disabled"}
    if not settings.get("operator_policy", "").strip():
        raise ValueError("Automatic publication requires an operator_policy record")
    day = now.astimezone(config.timezone).date().isoformat()
    record = store.data["discovery"].setdefault(day, {"queries": [], "added": 0})
    imports = record.setdefault("auto_import", {"checked_ids": [], "asset_ids": []})
    if len(imports["asset_ids"]) >= settings.get("max_auto_videos_per_day", 1):
        return {"status": "daily_import_limit"}
    search_status = discover(config, store, client, now)
    keywords = [word.casefold() for word in settings.get("keywords", ["奶蛙", "naiwa"])]
    candidates = sorted((asset for asset in store.data["assets"].values()
                         if asset["kind"] == "candidate" and asset["rights"] != "rejected"),
                        key=lambda asset: asset["added_at"], reverse=True)
    scratch.mkdir(parents=True, exist_ok=True)
    temporary = scratch / "web-video.pending"
    for candidate in candidates:
        if len(imports["checked_ids"]) >= settings.get("max_candidate_checks_per_day", 6):
            break
        if candidate["id"] in imports["checked_ids"] or candidate.get("auto_asset_id"):
            continue
        text = (candidate["title"] + " " + candidate.get("search_excerpt", "")).casefold()
        if not any(word in text for word in keywords):
            continue
        imports["checked_ids"].append(candidate["id"])
        candidate["auto_status"] = "checking"
        store.save()  # Limit fetches across runner restarts and hourly retries.
        try:
            media_url = find_video(client, candidate["source_url"])
            if not media_url:
                candidate["auto_status"] = "no_public_mp4"
                continue
            # Reserve enough room for a source and its normalized publication copy.
            size = sum(path.stat().st_size for path in (store.path / "media").glob("*") if path.is_file())
            if size > 240_000_000:
                raise ValueError("Insufficient media storage for automatic web import")
            download(client, media_url, temporary)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if any(asset.get("sha256") == digest for asset in store.data["assets"].values()):
                candidate["auto_status"] = "duplicate"
                continue
            validate_web_video(temporary)
            identity = asset_id("web", media_url + ":" + digest)
            relative = "media/" + digest + ".mp4"
            temporary.replace(store.path / relative)
            host = urlparse(candidate["source_url"]).hostname
            store.data["assets"][identity] = {
                "id": identity, "kind": "video", "title": candidate["title"],
                "url": media_url, "source_url": candidate["source_url"], "source_name": host,
                "local_path": "", "state_path": relative, "sha256": digest,
                "rights": "unverified", "evidence": settings["operator_policy"],
                "credit": "Source: " + host, "ai_generated": False, "ai_origin": "unknown",
                "reviewed": True, "approval_mode": "automatic_operator_policy", "added_at": now.isoformat()}
            candidate.update(auto_status="imported", auto_asset_id=identity)
            imports["asset_ids"].append(identity)
            return {"status": "imported", "asset_id": identity, "rights": "unverified"}
        except Exception as error:
            # Only our own errors may enter the public state; do not copy URLs/response bodies.
            candidate.update(auto_status="unavailable", auto_error=type(error).__name__)
        finally:
            temporary.unlink(missing_ok=True)
            store.save()
    return {"status": "no_usable_video", "search": search_status, "checked": len(imports["checked_ids"])}
