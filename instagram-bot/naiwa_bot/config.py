from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
import tomllib
from zoneinfo import ZoneInfo


@dataclass
class Config:
    root: Path
    data: dict

    @classmethod
    def load(cls, root: Path, path: Path | None = None):
        path = path or root / "instagram-bot/config.toml"
        cfg = cls(root.resolve(), tomllib.loads(path.read_text(encoding="utf-8")))
        ZoneInfo(cfg.schedule["timezone"])
        for key in ("story_hour", "feed_hour"):
            if not 0 <= cfg.schedule[key] <= 23:
                raise ValueError(f"Invalid {key}")
        if cfg.schedule["feed_every_days"] < 1 or cfg.schedule["reuse_after_days"] < 1:
            raise ValueError("Schedule intervals must be positive")
        if cfg.schedule["start_date"]:
            date.fromisoformat(cfg.schedule["start_date"])
        if not re.fullmatch(r"v\d+\.0", cfg.instagram["api_version"]):
            raise ValueError("Invalid Instagram API version")
        if not 1 <= cfg.ai["max_requests_per_day"] <= 3:
            raise ValueError("AI daily request limit must be 1..3")
        if not 1 <= cfg.discovery["max_results"] <= 10 or len(cfg.discovery["queries"]) > 3:
            raise ValueError("Discovery is limited to three queries and ten results per query")
        if type(cfg.discovery.get("auto_publish", False)) is not bool:
            raise ValueError("Discovery auto_publish must be a boolean")
        if cfg.discovery.get("auto_publish", False) and not cfg.discovery.get("operator_policy", "").strip():
            raise ValueError("Automatic publication requires an operator_policy record")
        if not 1 <= cfg.discovery.get("max_auto_videos_per_day", 1) <= 3:
            raise ValueError("Automatic web imports must be limited to 1..3 videos per day")
        if not 1 <= cfg.discovery.get("max_candidate_checks_per_day", 6) <= 18:
            raise ValueError("Candidate checks must be limited to 1..18 per day")
        keywords = cfg.discovery.get("keywords", ["奶蛙", "naiwa"])
        if not keywords or any(not isinstance(word, str) or not word.strip() for word in keywords):
            raise ValueError("Discovery keywords must contain nonempty strings")
        return cfg

    @property
    def instagram(self):
        return self.data["instagram"]

    @property
    def schedule(self):
        return self.data["schedule"]

    @property
    def discovery(self):
        return self.data["discovery"]

    @property
    def ai(self):
        return self.data["ai"]

    @property
    def timezone(self):
        return ZoneInfo(self.schedule["timezone"])


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Path must stay inside the repository")
    return path
