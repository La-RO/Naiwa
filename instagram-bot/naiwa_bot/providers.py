import base64
from datetime import datetime, timedelta, timezone
import hashlib
import os
import secrets
from urllib.parse import urlencode

from cryptography.fernet import Fernet

from .catalogue import asset_id
from .config import inside
from .network import RemoteError, checked_json


class Instagram:
    def __init__(self, config, store, client):
        self.config, self.store, self.client = config, store, client
        self.base = f"https://graph.instagram.com/{config.instagram['api_version']}"
        key = os.environ.get("BOT_ENCRYPTION_KEY", "")
        if not key:
            raise ValueError("Set BOT_ENCRYPTION_KEY in GitHub Secrets")
        self.cipher = Fernet(key.encode())
        account = store.data["account"]
        if account:
            self.token = self.cipher.decrypt(account["encrypted_token"].encode()).decode()
            self.user_id = account["user_id"]
        else:
            self.token = os.environ.get("IG_ACCESS_TOKEN", "")
            self.user_id = os.environ.get("IG_USER_ID", "")
        if not self.token:
            raise ValueError("Set a long-lived IG_ACCESS_TOKEN in GitHub Secrets")

    def request(self, method, path, **kwargs):
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            result = self.client.request(method, f"{self.base}/{path}", headers=headers, timeout=60, **kwargs)
        except Exception:
            raise RemoteError("Instagram network request failed; inspect the publication journal") from None
        return checked_json(result)

    def verify(self, now):
        info = self.request("GET", "me", params={"fields": "user_id,username,account_type"})
        if info.get("username", "").lower() != self.config.instagram["username"].lower():
            raise ValueError("Instagram token belongs to a different username")
        user_id = str(info.get("user_id") or info.get("id") or "")
        if not user_id or (self.user_id and self.user_id != user_id):
            raise ValueError("IG_USER_ID does not match the token account")
        if info.get("account_type") != "BUSINESS":
            raise ValueError("Daily Stories require an Instagram Business account")
        self.user_id = user_id
        previous = self.store.data["account"]
        if previous and now - datetime.fromisoformat(previous["refreshed_at"]) >= timedelta(days=7):
            try:
                response = self.client.get("https://graph.instagram.com/refresh_access_token",
                    params={"grant_type": "ig_refresh_token", "access_token": self.token}, timeout=60)
            except Exception:
                raise RemoteError("Instagram token refresh failed") from None
            renewed = checked_json(response)
            self.token = renewed["access_token"]
            previous = None
        if previous is None:
            self.store.data["account"] = {"user_id": user_id, "username": info["username"],
                "encrypted_token": self.cipher.encrypt(self.token.encode()).decode(), "refreshed_at": now.isoformat()}
            self.store.save()

        return {"user_id": user_id, "username": info["username"], "account_type": info["account_type"]}

    def create(self, job, asset, media_url):
        payload = {"video_url" if asset["kind"] == "video" else "image_url": media_url}
        if job["channel"] == "story":
            payload["media_type"] = "STORIES"
        else:
            payload["caption"] = caption(asset)
            if asset["kind"] == "video":
                payload.update(media_type="REELS", share_to_feed="true")
        # AI disclosure is burned into all generated media. The API AI label
        # field varies by version; no unsupported field is silently assumed.
        return self.request("POST", f"{self.user_id}/media", data=payload)["id"]

    def status(self, container_id):
        return self.request("GET", container_id, params={"fields": "status_code,status"}).get("status_code")

    def publish(self, container_id):
        return self.request("POST", f"{self.user_id}/media_publish", data={"creation_id": container_id})["id"]


def caption(asset):
    text = f"{asset['title']} 🐸\n奶蛙今天也在认真可爱。\n\n"
    if asset["ai_generated"]:
        text += "AI 生成 · 虚构奶蛙日常 / AI-generated fictional daily life\n"
    text += f"Credit: {asset['credit']}\n来源: {asset['source_url']}\n#奶蛙 #Naiwa #NaiwaClub"
    if len(text) > 2200:
        raise ValueError("Caption exceeds Instagram's length limit")
    return text


def discover(config, store, client, now):
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        return "Search skipped: TAVILY_API_KEY is not configured"
    day = now.astimezone(config.timezone).date().isoformat()
    record = store.data["discovery"].setdefault(day, {"queries": [], "added": 0})
    for query in config.discovery["queries"]:
        if query in record["queries"]:
            continue
        # Persist before a billed call: a timeout must not create unbounded charges.
        record["queries"].append(query)
        store.save()
        response = client.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {key}"},
            json={"query": query, "search_depth": "basic", "max_results": config.discovery["max_results"],
                  "include_answer": False, "include_images": False, "safe_search": True}, timeout=60)
        data = checked_json(response)
        for result in data.get("results", []):
            url = result.get("url", "")
            if not url.startswith("https://"):
                continue
            identity = asset_id("candidate", url)
            if identity in store.data["assets"]:
                continue
            store.data["assets"][identity] = {"id": identity, "kind": "candidate", "title": result.get("title", "Untitled")[:200],
                "url": "", "source_url": url, "local_path": "", "sha256": "", "rights": "pending", "evidence": "",
                "credit": "", "ai_generated": False, "reviewed": False, "added_at": now.isoformat(),
                "search_excerpt": str(result.get("content", ""))[:1500]}
            record["added"] += 1
        store.save()
    return f"Search candidates added today: {record['added']}"


def generate_video(config, store, client, now):
    settings = config.ai
    if not settings["enabled"]:
        return None
    if not settings["character_rights_confirmed"]:
        raise ValueError("Confirm character/reference rights in config.toml before AI generation")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("Set GEMINI_API_KEY to enable AI video generation")
    if not settings["reference_image"]:
        raise ValueError("Set a licensed reference_image to preserve Naiwa's appearance")
    reference = inside(config.root, settings["reference_image"])
    if reference.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp") or reference.stat().st_size > 8_000_000:
        raise ValueError("AI reference must be an image under 8 MB")
    day = now.astimezone(config.timezone).date().isoformat()
    requests = store.data["ai_requests"].setdefault(day, [])
    if len(requests) >= settings["max_requests_per_day"]:
        return None
    sequence = len(requests)
    request_id = asset_id("ai", f"{day}:{sequence}")
    record = {"id": request_id, "status": "requested", "model": settings["model"], "at": now.isoformat()}
    requests.append(record)
    store.save()
    scenes = settings["daily_scenes"]
    scene = scenes[now.astimezone(config.timezone).date().toordinal() % len(scenes)]
    prompt = (f"Create an 8-second animated fictional daily-life video. Preserve the exact mascot in the reference: "
              f"{settings['character_description']}. Scene: {scene}. Warm humorous wholesome cartoon, "
              "one coherent action, gentle camera, no dialogue, no logos, no text. This is fictional animation.")
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[reference.suffix.lower()]
    try:
        response = client.post("https://generativelanguage.googleapis.com/v1beta/interactions",
            headers={"x-goog-api-key": api_key}, json={"model": settings["model"],
                "input": [{"type": "image", "mime_type": mime, "data": base64.b64encode(reference.read_bytes()).decode()},
                          {"type": "text", "text": prompt}],
                "response_format": {"type": "video", "aspect_ratio": "9:16", "resolution": "720p"}}, timeout=900)
        data = checked_json(response)
        videos = [part for step in data.get("steps", []) if step.get("type") == "model_output"
                  for part in step.get("content", []) if part.get("type") == "video" and part.get("data")]
        if data.get("status") != "completed" or not videos:
            raise RemoteError("Video provider did not return a completed inline video")
        content = base64.b64decode(videos[0]["data"], validate=True)
        if not content or len(content) > 80_000_000:
            raise ValueError("Generated video exceeds media limit or is empty")
        digest = hashlib.sha256(content).hexdigest()
        path = "media/" + digest + ".mp4"
        (store.path / path).write_bytes(content)
        approved = settings["auto_approve"]
        asset = {"id": request_id, "kind": "video", "title": f"奶蛙虚构日常 · {day}",
                 "url": "", "source_url": "https://github.com/La-RO/Naiwa", "state_path": path,
                 "local_path": "", "sha256": digest, "rights": "ai" if approved else "pending",
                 "evidence": "Configured character rights confirmation; " + settings["model"] if approved else "",
                 "credit": "Naiwa Club / AI-generated", "ai_generated": True, "reviewed": approved,
                 "added_at": now.isoformat(), "prompt": prompt, "model": settings["model"],
                 "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest()}
        store.data["assets"][request_id] = asset
        record.update(status="completed", asset_id=request_id)
        store.save()
        return asset
    except Exception:
        record["status"] = "failed_or_unknown"
        store.save()
        raise RemoteError("AI generation failed or timed out; daily request reservation retained") from None


def oauth_url(config, store):
    app_id, redirect = os.environ["IG_APP_ID"], os.environ["IG_REDIRECT_URI"]
    state = secrets.token_urlsafe(32)
    store.data["oauth"] = {"hash": hashlib.sha256(state.encode()).hexdigest(),
                           "created_at": datetime.now(timezone.utc).isoformat()}
    store.save()
    return "https://www.instagram.com/oauth/authorize?" + urlencode({"client_id": app_id,
        "redirect_uri": redirect, "response_type": "code", "scope": "instagram_business_basic,instagram_business_content_publish",
        "enable_fb_login": "0", "force_authentication": "1", "state": state})


def oauth_exchange(config, store, client, now):
    pending = store.data["oauth"]
    returned = os.environ.get("IG_OAUTH_STATE", "")
    if not pending or now - datetime.fromisoformat(pending["created_at"]) > timedelta(minutes=15):
        raise ValueError("OAuth request missing/expired; run oauth-url again")
    if not secrets.compare_digest(pending["hash"], hashlib.sha256(returned.encode()).hexdigest()):
        raise ValueError("OAuth state mismatch")
    code = os.environ["IG_OAUTH_CODE"].removesuffix("#_")
    store.data["oauth"] = None
    store.save()
    short = checked_json(client.post("https://api.instagram.com/oauth/access_token", data={
        "client_id": os.environ["IG_APP_ID"], "client_secret": os.environ["IG_APP_SECRET"],
        "grant_type": "authorization_code", "redirect_uri": os.environ["IG_REDIRECT_URI"], "code": code}, timeout=60))
    long = checked_json(client.get("https://graph.instagram.com/access_token", params={"grant_type": "ig_exchange_token",
        "client_secret": os.environ["IG_APP_SECRET"], "access_token": short["access_token"]}, timeout=60))
    # Encrypt directly; tokens never appear in stdout or workflow artifacts.
    cipher = Fernet(os.environ["BOT_ENCRYPTION_KEY"].encode())
    store.data["account"] = {"user_id": str(short["user_id"]), "username": config.instagram["username"],
        "encrypted_token": cipher.encrypt(long["access_token"].encode()).decode(), "refreshed_at": now.isoformat()}
    Instagram(config, store, client).verify(now)
    store.save()
