import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv
import httpx

from .catalogue import add_asset, approve, import_catalogue
from .config import Config
from .engine import due_slots, preview, run, safe_error
from .network import checked_json, download
from .providers import Instagram, discover, oauth_exchange, oauth_url
from .state import GitStore, Store


COMMANDS = ("preview", "status", "check", "run", "pause", "resume", "import", "discover", "add", "approve", "reject", "retry", "reconcile", "abandon", "oauth-url", "oauth-exchange")


def markdown(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace(">", "&gt;")


def summary(config, store, now, result):
    counts = Counter(a["rights"] for a in store.data["assets"].values())
    text = ["# 奶蛙 Instagram 机器人", "", f"账号：`{config.instagram['username']}` · 状态：{'暂停' if store.data['paused'] else '运行'}",
            f"本地时间：{now.astimezone(config.timezone).isoformat()} · 时区：{config.schedule['timezone']}",
            f"Story：每日 {config.schedule['story_hour']:02d}:00 · Feed：每 {config.schedule['feed_every_days']} 天 {config.schedule['feed_hour']:02d}:00",
            f"排期起点：{config.schedule['start_date'] or store.data['start_date'] or '恢复时确定'}", "",
            f"素材授权：{dict(counts)}", "", "## 本次结果", "", "```json", json.dumps(result, ensure_ascii=False, indent=2), "```", "",
            "## 待审核素材 / 搜索候选", "", "| 素材 ID | 类型 | 标题 | 来源 |", "| --- | --- | --- | --- |"]
    for asset in list(store.data["assets"].values())[-100:]:
        if not asset["reviewed"] and asset["rights"] != "rejected":
            text.append("| " + " | ".join(markdown(asset.get(k, "")) for k in ("id", "kind", "title", "source_url")) + " |")
    text += ["", "## 最近发布记录", "", "| 时段 ID | 状态 | 素材 ID | Instagram 媒体 ID | 视频生成说明 |", "| --- | --- | --- | --- | --- |"]
    for slot, job in sorted(store.data["jobs"].items(), reverse=True)[:30]:
        text.append("| " + " | ".join(markdown(v) for v in (slot, job["status"], job.get("asset_id", ""), job.get("media_id", ""), job.get("generation_reason", ""))) + " |")
    automatic = config.discovery.get("auto_publish", False)
    text += ["", "网络自动发布：" + ("已开启；转载权利未核实，依据运营者策略发布。" if automatic else "关闭；搜索结果需审核。"),
             "备用生成：Runway Gen-4 Turbo；已有视频优先，缺片才请求。generating 表示等待同一个生成任务。",
             "pending 素材不会自动发布。AI 内容在画面中标注为虚构日常。",
             "GitHub 定时任务可能延迟；机器人仅执行当天时段，不补发过去日期。", ""]
    return "\n".join(text)


def execute(command, payload, config, store, client, now, scratch):
    if command in ("preview", "status"):
        if command == "preview":
            import_catalogue(store, config.root)  # memory only, no save/network/paid calls
            return preview(config, store, now)
        return {"paused": store.data["paused"], "assets": len(store.data["assets"]), "jobs": len(store.data["jobs"])}
    if command == "check":
        account = Instagram(config, store, client).verify(now)
        return {"connected": True, "account": account, "paused": store.data["paused"], "publishing_tested": False}
    if command == "run":
        if not isinstance(store, GitStore):
            raise ValueError("Live publishing is available only with --github-state")
        return run(config, store, client, now, scratch)
    if command == "pause":
        store.data["paused"] = True
    elif command == "resume":
        store.data["paused"] = False
        if not store.data["start_date"]:
            store.data["start_date"] = now.astimezone(config.timezone).date().isoformat()
    elif command == "import":
        result = {"imported": import_catalogue(store, config.root)}
        store.save()
        return result
    elif command == "add":
        scratch.mkdir(parents=True, exist_ok=True)
        source = scratch / "review-download"
        download(client, payload["url"], source)
        payload = dict(payload, sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        result = {"asset_id": add_asset(store, payload)}
        store.save()
        return result
    elif command == "approve":
        approve(store, payload)
    elif command == "reject":
        keys = payload.get("asset_ids", [])
        if not keys:
            raise ValueError("Provide asset_ids")
        assets = [store.data["assets"][key] for key in keys]
        for asset in assets:
            asset.update(rights="rejected", reviewed=False)
    elif command == "discover":
        return {"discovery": discover(config, store, client, now)}
    elif command in ("retry", "reconcile", "abandon"):
        job = store.data["jobs"][payload["slot"]]
        if command == "reconcile":
            if job["status"] != "needs_review" or not re.fullmatch(r"\d+", str(payload.get("media_id", ""))) or not payload.get("evidence"):
                raise ValueError("Reconcile requires needs_review status, media_id and inspection evidence")
            job.update(status="published", media_id=str(payload["media_id"]), published_at=now.isoformat(),
                       reconciliation_evidence=payload["evidence"], error="")
        elif command == "abandon":
            if job["status"] == "published" or not payload.get("evidence"):
                raise ValueError("Cannot abandon a published slot; inspection evidence is required")
            # Keep this asset reserved: an unknown publish may actually be live.
            if job["status"] in ("publishing", "needs_review"):
                job["uncertain_publish"] = True
                asset = store.data["assets"].get(job.get("asset_id"))
                if asset:
                    asset.update(rights="rejected", reviewed=False)
            job.update(status="abandoned", reconciliation_evidence=payload["evidence"])
        else:
            if job["status"] != "failed":
                raise ValueError("Retry is only allowed for a failed PRE-publish operation")
            job.update(status="planned", attempts=0, error="")
    elif command == "oauth-url":
        if isinstance(store, GitStore):
            raise ValueError("OAuth helpers run locally; do not expose authorization URLs in Actions logs")
        return {"authorization_url": oauth_url(config, store)}
    elif command == "oauth-exchange":
        if isinstance(store, GitStore):
            raise ValueError("OAuth helpers run locally")
        oauth_exchange(config, store, client, now)
        return {"bound": config.instagram["username"], "token": "encrypted in local state.json"}
    store.save()
    return {"command": command, "ok": True}


def main():
    parser = argparse.ArgumentParser(description="Naiwa Instagram bot controlled by GitHub Actions")
    parser.add_argument("command", nargs="?", choices=COMMANDS)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--state", type=Path, default=Path("state"))
    parser.add_argument("--scratch", type=Path, default=Path("scratch"))
    parser.add_argument("--github-state", action="store_true")
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    command = args.command or os.environ.get("BOT_COMMAND", "preview")
    if command not in COMMANDS:
        parser.error("Unknown command")
    config = Config.load(args.root)
    now = datetime.now(timezone.utc)
    store = None
    result = {}
    failed = False
    with httpx.Client(follow_redirects=False, trust_env=False) as client:
        try:
            if args.github_state:
                repository, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
                repo = checked_json(client.get(f"https://api.github.com/repos/{repository}", headers={"Authorization": f"Bearer {token}"}, timeout=60))
                if repo.get("private"):
                    raise ValueError("This version uses public GitHub media URLs and requires a public repository")
                store = GitStore(args.state, repository, token)
            else:
                store = Store(args.state)
            payload = json.loads(os.environ.get("BOT_PAYLOAD", "{}") or "{}")
            if not isinstance(payload, dict):
                raise ValueError("Payload must be a JSON object")
            result = execute(command, payload, config, store, client, now, args.scratch)
            if isinstance(result, dict):
                failed = "discovery_error" in result or any(
                    key.startswith(("story:", "feed:")) and value not in ("published", "waiting")
                    for key, value in result.items())
        except Exception as error:
            result = {"error": safe_error(error)}
            failed = True
        finally:
            if store is not None:
                text = summary(config, store, now, result)
                Path("summary.md").write_text(text, encoding="utf-8")
                if os.environ.get("GITHUB_STEP_SUMMARY"):
                    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
                        output.write(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if failed:
        print("::error::Naiwa bot requires attention. Read the run summary and publication journal.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
