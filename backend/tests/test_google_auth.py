import json
import stat
from datetime import UTC, datetime, timedelta

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from pydantic import SecretStr

from app.sync import google_auth
from app.sync.google_auth import (
    SCOPES,
    NotConfigured,
    OAuthClient,
    ReconnectNeeded,
    disconnect,
    load,
    missing_scopes,
    save,
)

# Made-up values; nothing here talks to Google.
CLIENT = OAuthClient("test-client.apps.googleusercontent.com", "test-secret")


def credentials(expired: bool = False, refresh_token: str | None = "refresh") -> Credentials:
    expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=-1 if expired else 1)
    return Credentials(
        token="access",
        refresh_token=refresh_token,
        token_uri=google_auth.TOKEN_URI,
        client_id=CLIENT.client_id,
        client_secret=CLIENT.client_secret,
        scopes=list(SCOPES),
        expiry=expiry,
    )


@pytest.mark.parametrize(
    "client_id, client_secret",
    [
        (None, None),
        (SecretStr("id"), None),
        (SecretStr(""), SecretStr("secret")),
        (SecretStr(" "), SecretStr("secret")),
    ],
)
def test_missing_client_settings_are_reported(client_id, client_secret):
    with pytest.raises(NotConfigured, match="FA_GOOGLE_CLIENT_ID"):
        OAuthClient.from_settings(client_id, client_secret)


def test_client_config_uses_the_loopback_redirect():
    client = OAuthClient.from_settings(SecretStr(" id "), SecretStr("secret"))
    installed = client.config()["installed"]
    assert installed["client_id"] == "id"
    assert installed["redirect_uris"] == ["http://localhost"]


def test_asks_only_for_read_only_health_scopes():
    assert len(SCOPES) == 4
    assert all(s.startswith(google_auth.SCOPE_PREFIX) and s.endswith(".readonly") for s in SCOPES)


def test_reports_scopes_the_user_did_not_grant():
    assert missing_scopes(SCOPES) == []
    assert missing_scopes(None) == list(SCOPES)
    assert missing_scopes(SCOPES[:2]) == list(SCOPES[2:])


def test_saved_token_is_readable_only_by_its_owner(tmp_path):
    token_file = tmp_path / "nested" / "token.json"
    save(credentials(), token_file)
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    token_file.chmod(0o644)
    save(credentials(), token_file)
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_valid_token_loads_without_refreshing(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    save(credentials(), token_file)
    monkeypatch.setattr(Credentials, "refresh", lambda *_: pytest.fail("should not refresh"))
    assert load(token_file).token == "access"


def test_expired_token_is_refreshed_and_saved(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    save(credentials(expired=True), token_file)

    def refresh(self, _request):
        self.token = "renewed"
        self.expiry = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)

    monkeypatch.setattr(Credentials, "refresh", refresh)
    assert load(token_file).token == "renewed"
    assert json.loads(token_file.read_text())["token"] == "renewed"


def test_failed_refresh_asks_to_reconnect(tmp_path, monkeypatch):
    token_file = tmp_path / "token.json"
    save(credentials(expired=True), token_file)

    def refresh(self, _request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.")

    monkeypatch.setattr(Credentials, "refresh", refresh)
    with pytest.raises(ReconnectNeeded, match="7 days"):
        load(token_file)


def test_token_without_refresh_token_asks_to_reconnect(tmp_path):
    token_file = tmp_path / "token.json"
    save(credentials(expired=True, refresh_token=None), token_file)
    with pytest.raises(ReconnectNeeded, match="incomplete"):
        load(token_file)


def test_missing_or_corrupt_token_asks_to_reconnect(tmp_path):
    token_file = tmp_path / "token.json"
    with pytest.raises(ReconnectNeeded, match="Not connected"):
        load(token_file)
    token_file.write_text("{not json")
    with pytest.raises(ReconnectNeeded, match="unreadable"):
        load(token_file)


def test_disconnect_forgets_the_sign_in(tmp_path):
    token_file = tmp_path / "token.json"
    save(credentials(), token_file)
    assert disconnect(token_file) is True
    assert not token_file.exists()
    assert disconnect(token_file) is False
