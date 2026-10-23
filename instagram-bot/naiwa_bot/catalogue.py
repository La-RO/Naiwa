from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from .config import inside


PUBLISHABLE_RIGHTS = ("owned", "permission", "licensed", "ai", "unverified")


def publishable(asset):
    return (asset.get("reviewed") and asset.get("rights") in PUBLISHABLE_RIGHTS
            and (asset["rights"] != "unverified" or asset.get("approval_mode") == "automatic_operator_policy"))


def asset_id(prefix: str, value: str):
    return prefix + ":" + hashlib.sha256(value.encode()).hexdigest()[:20]


def import_catalogue(store, root: Path):
    added = 0
    for name, kind in (("images", "image"), ("videos", "video")):
        items = json.loads((root / f"data/{name}.json").read_text(encoding="utf-8"))
        for item in items:
            key = "repo:" + item["id"]
            if key in store.data["assets"]:
                continue
            path = inside(root, item["src"])
            if not path.is_file():
                raise ValueError(f"Missing catalogue file: {item['src']}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            # The website explicitly says reuse authorization is unverified.
            store.data["assets"][key] = {
                "id": key, "kind": kind, "title": item["title"], "local_path": item["src"],
                "source_url": item["sourceUrl"], "source_name": item["sourceName"],
                "source_note": item.get("sourceNote", ""), "url": "", "sha256": digest,
                "rights": "pending", "evidence": "", "credit": "", "ai_generated": False,
                "reviewed": False, "added_at": datetime.now(timezone.utc).isoformat()}
            added += 1
    return added


def add_asset(store, payload):
    for key in ("url", "source_url", "title", "kind"):
        if not payload.get(key):
            raise ValueError(f"Missing {key}")
    if payload["kind"] not in ("image", "video"):
        raise ValueError("kind must be image or video")
    for key in ("url", "source_url"):
        parsed = urlparse(payload[key])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError(f"{key} must be a public HTTPS URL")
    key = asset_id("web", payload["url"] + ":" + payload.get("sha256", ""))
    if key not in store.data["assets"]:
        store.data["assets"][key] = {"id": key, "kind": payload["kind"], "title": payload["title"],
            "url": payload["url"], "source_url": payload["source_url"], "local_path": "", "sha256": payload.get("sha256", ""),
            "rights": "pending", "evidence": "", "credit": "", "ai_generated": bool(payload.get("ai_generated", False)),
            "reviewed": False, "added_at": datetime.now(timezone.utc).isoformat()}
    return key


def approve(store, payload):
    keys = payload.get("asset_ids", [])
    if not keys or not isinstance(keys, list):
        raise ValueError("asset_ids must be a nonempty list")
    if payload.get("rights") not in ("owned", "permission", "licensed", "ai"):
        raise ValueError("rights must be owned, permission, licensed or ai")
    if not payload.get("evidence", "").strip() or not payload.get("credit", "").strip():
        raise ValueError("Authorization evidence/reference and attribution are required")
    assets = [store.data["assets"][key] for key in keys]
    if any(a["kind"] not in ("image", "video") for a in assets):
        raise ValueError("Search pages are candidates; add a direct media URL before approval")
    if any(a["ai_generated"] != (payload["rights"] == "ai") for a in assets):
        raise ValueError("AI assets require rights=ai; non-AI assets require ownership/permission/license")
    for asset in assets:
        asset.update(rights=payload["rights"], evidence=payload["evidence"], credit=payload["credit"], reviewed=True)


def eligible(store, channel, now, reuse_days):
    cutoff = now - timedelta(days=reuse_days)
    reserved_ids = set()
    reserved_hashes = set()
    for job in store.data["jobs"].values():
        if job.get("asset_id") and job["status"] != "blocked" and (job["status"] != "abandoned" or job.get("uncertain_publish")):
            if job["status"] != "published" or datetime.fromisoformat(job["published_at"]) > cutoff:
                reserved_ids.add(job["asset_id"])
                if job.get("sha256"):
                    reserved_hashes.add(job["sha256"])
    found = []
    for asset in store.data["assets"].values():
        if channel == "story" and asset["kind"] != "video":
            continue
        if asset["kind"] not in ("image", "video") or not publishable(asset):
            continue
        if not asset["evidence"] or not asset["credit"] or asset["id"] in reserved_ids:
            continue
        if asset.get("sha256") and asset["sha256"] in reserved_hashes:
            continue
        found.append(asset)
    # Alternate feed images and Reels, where both have eligible material.
    if channel == "feed":
        previous = [j for j in store.data["jobs"].values() if j["channel"] == "feed" and j["status"] == "published"]
        previous.sort(key=lambda j: j["published_at"])
        desired = "image" if previous and previous[-1]["kind"] == "video" else "video"
        found.sort(key=lambda a: (a["kind"] != desired, a["added_at"], a["id"]))
    else:
        found.sort(key=lambda a: (a["added_at"], a["id"]))
    return found
