import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from cryptography.fernet import Fernet
import httpx
import pytest

from naiwa_bot.__main__ import execute
from naiwa_bot.config import Config
from naiwa_bot.network import RemoteError
from naiwa_bot.providers import Instagram
from naiwa_bot.state import Store


ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 24, 5, 0, tzinfo=timezone.utc)
PROFILE = {"user_id": "123", "username": "unimelb.naiwaclub", "account_type": "BUSINESS"}


class Journal(Store):
    def __init__(self, path):
        super().__init__(path)
        self.snapshots = []

    def save(self):
        super().save()
        self.snapshots.append(copy.deepcopy(self.data))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    cipher = Fernet(key)
    monkeypatch.setenv("BOT_ENCRYPTION_KEY", key.decode())
    monkeypatch.setenv("IG_ACCESS_TOKEN", "new-secret-token")
    monkeypatch.setenv("IG_USER_ID", "123")
    store = Journal(tmp_path / "state")
    store.data.update(paused=True, start_date="2026-10-23")
    store.data["account"] = {"user_id": "123", "username": PROFILE["username"],
        "encrypted_token": cipher.encrypt(b"old-cached-token").decode(), "refreshed_at": (NOW - timedelta(days=1)).isoformat()}
    store.data["assets"]["existing"] = {"rights": "permission", "reviewed": True}
    store.data["jobs"]["story:2026-10-23"] = {"status": "published", "media_id": "456"}
    return Config.load(ROOT), store, cipher, tmp_path


def test_default_check_keeps_the_cached_token(setup):
    cfg, store, cipher, folder = setup
    before = copy.deepcopy(store.data)
    def handler(request):
        assert request.headers["authorization"] == "Bearer old-cached-token"
        return httpx.Response(200, json=PROFILE)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute("check", {}, cfg, store, client, NOW, folder / "scratch")
    assert result["connected"] and not result.get("binding_updated")
    assert store.data == before and not store.snapshots


def test_explicit_check_verifies_secret_before_replacing_account(setup):
    cfg, store, cipher, folder = setup
    before = copy.deepcopy(store.data)
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET" and request.url.path.endswith("/me")
        assert request.headers["authorization"] == "Bearer new-secret-token"
        assert store.data == before and not store.snapshots
        return httpx.Response(200, json=PROFILE)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = execute("check", {"use_secret_token": True}, cfg, store, client, NOW, folder / "scratch")
    assert len(requests) == 1
    assert result["binding_updated"] and result["token_source"] == "IG_ACCESS_TOKEN"
    assert result["paused"] and not result["publishing_tested"]
    assert cipher.decrypt(store.data["account"]["encrypted_token"].encode()) == b"new-secret-token"
    assert store.data["account"]["refreshed_at"] == NOW.isoformat()
    for field in before:
        if field != "account":
            assert store.data[field] == before[field]
    assert "new-secret-token" not in json.dumps(store.data) + json.dumps(result)
    assert not (folder / "scratch").exists()


@pytest.mark.parametrize("profile, expected", [
    (dict(PROFILE, username="other-account"), "different username"),
    (dict(PROFILE, user_id="999"), "IG_USER_ID"),
    (dict(PROFILE, account_type="MEDIA_CREATOR"), "Business account"),
])
def test_new_token_for_wrong_account_never_overwrites_saved_binding(setup, profile, expected):
    cfg, store, cipher, folder = setup
    before = copy.deepcopy(store.data)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=profile))) as client:
        with pytest.raises(ValueError, match=expected):
            execute("check", {"use_secret_token": True}, cfg, store, client, NOW, folder / "scratch")
    assert store.data == before and not store.snapshots


def test_permission_error_preserves_old_account_and_hides_remote_message(setup):
    cfg, store, cipher, folder = setup
    before = copy.deepcopy(store.data)
    def handler(request):
        return httpx.Response(400, json={"error": {"code": 200, "message": "secret token new-secret-token"}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RemoteError) as result:
            execute("check", {"use_secret_token": True}, cfg, store, client, NOW, folder / "scratch")
    assert str(result.value) == "Instagram account verification: Remote API returned HTTP 400 (code=200)"
    assert "new-secret-token" not in str(result.value)
    assert store.data == before and not store.snapshots


def test_missing_secret_never_silently_falls_back_to_cached_token(setup, monkeypatch):
    cfg, store, cipher, folder = setup
    monkeypatch.delenv("IG_ACCESS_TOKEN")
    before = copy.deepcopy(store.data)
    with pytest.raises(ValueError, match="IG_ACCESS_TOKEN"):
        execute("check", {"use_secret_token": True}, cfg, store, None, NOW, folder / "scratch")
    assert store.data == before


def test_explicit_rebind_does_not_need_to_decrypt_old_invalid_ciphertext(setup):
    cfg, store, cipher, folder = setup
    store.data["account"]["encrypted_token"] = "unreadable-old-ciphertext"
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=PROFILE))) as client:
        result = execute("check", {"use_secret_token": True}, cfg, store, client, NOW, folder / "scratch")
    assert result["binding_updated"]
    assert cipher.decrypt(store.data["account"]["encrypted_token"].encode()) == b"new-secret-token"


@pytest.mark.parametrize("value", ["true", 1, None])
def test_rebind_requires_an_explicit_boolean(setup, value):
    cfg, store, cipher, folder = setup
    with pytest.raises(ValueError, match="JSON boolean"):
        execute("check", {"use_secret_token": value}, cfg, store, None, NOW, folder / "scratch")
    assert not store.snapshots


def test_default_weekly_refresh_still_keeps_refreshed_token_over_old_secret(setup):
    cfg, store, cipher, folder = setup
    store.data["account"]["refreshed_at"] = (NOW - timedelta(days=8)).isoformat()
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/me"):
            expected = "old-cached-token" if len(requests) == 1 else "renewed-token"
            assert request.headers["authorization"] == "Bearer " + expected
            return httpx.Response(200, json=PROFILE)
        assert request.url.path == "/refresh_access_token"
        assert request.url.params["access_token"] == "old-cached-token"
        return httpx.Response(200, json={"access_token": "renewed-token"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        execute("check", {}, cfg, store, client, NOW, folder / "scratch")
        Instagram(cfg, store, client).verify(NOW + timedelta(hours=1))
    assert len(requests) == 3
    assert requests[-1].headers["authorization"] == "Bearer renewed-token"
    assert cipher.decrypt(store.data["account"]["encrypted_token"].encode()) == b"renewed-token"
