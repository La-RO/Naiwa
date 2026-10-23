import base64
import copy
import json
import os
from pathlib import Path
import re
import subprocess


def initial_state():
    return {"schema": 1, "paused": True, "start_date": "", "assets": {}, "jobs": {},
            "discovery": {}, "ai_requests": {}, "account": None, "oauth": None}


class Store:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        (self.path / "media").mkdir(exist_ok=True)
        state_file = self.path / "state.json"
        self.data = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else initial_state()
        if self.data["schema"] != 1:
            raise ValueError("Unsupported state schema")

    def save(self):
        temporary = self.path / "state.tmp"
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path / "state.json")

    def public_url(self, relative: str):
        raise ValueError("Publishing requires --github-state and a public GitHub repository")


class GitStore(Store):
    branch = "naiwa-bot-state"

    def __init__(self, path: Path, repository: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
            raise ValueError("GitHub repository and GITHUB_TOKEN are required")
        self.repository = repository
        self.git_env = os.environ.copy()
        authorization = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        self.git_env.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
                             "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {authorization}"})
        self.path = path.resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        if not (self.path / ".git").exists():
            self.git("init", "-b", self.branch)
            self.git("remote", "add", "origin", f"https://github.com/{repository}.git")
        self.git("config", "user.name", "naiwa-bot[bot]")
        self.git("config", "user.email", "naiwa-bot@users.noreply.github.com")
        exists = self.git("ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{self.branch}", check=False)
        if exists.returncode == 0:
            self.git("fetch", "--depth", "1", "origin", f"refs/heads/{self.branch}")
            self.git("checkout", "-B", self.branch, "FETCH_HEAD")
        elif exists.returncode != 2:
            raise RuntimeError("Cannot read GitHub state branch; check token/network")
        super().__init__(path)
        self.last_saved = None

    def git(self, *args, check=True):
        result = subprocess.run(["git", "-C", str(self.path), *args], env=self.git_env,
                                capture_output=True, text=True, timeout=120)
        if check and result.returncode:
            # Never expose git stderr, which can include credentials/URLs.
            raise RuntimeError(f"Git state operation failed ({args[0]}); publishing stopped")
        return result

    def save(self):
        media_size = sum(p.stat().st_size for p in (self.path / "media").glob("*") if p.is_file())
        if media_size > 400_000_000:
            raise ValueError("Media storage exceeds 400 MB; archive media before continuing")
        super().save()
        self.git("add", "--", "state.json", "media")
        changed = self.git("diff", "--cached", "--quiet", check=False)
        if changed.returncode == 1:
            self.git("commit", "-m", "bot: persist publication journal [skip ci]")
        elif changed.returncode != 0:
            raise RuntimeError("Cannot inspect staged state")
        # Also retry a previous failed push; never force-push over another writer.
        self.git("push", "origin", f"HEAD:refs/heads/{self.branch}")
        self.last_saved = copy.deepcopy(self.data)

    def public_url(self, relative: str):
        if not re.fullmatch(r"media/[a-f0-9-]+\.(jpg|mp4)", relative):
            raise ValueError("Invalid generated media path")
        sha = self.git("rev-parse", "HEAD").stdout.strip()
        return f"https://raw.githubusercontent.com/{self.repository}/{sha}/{relative}"
