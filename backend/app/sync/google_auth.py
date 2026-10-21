"""Signing in to the Google Health API.

Uses Google's loopback flow for desktop apps: the browser signs in and redirects to a temporary
server on localhost, so the client secret stays on this machine. The refresh token is kept in a
git-ignored file only its owner can read. Per-user sign-in from the phone comes with accounts and
deployment, since it needs the backend on a public HTTPS address.

While the OAuth app is in Testing mode, Google expires refresh tokens after 7 days; that surfaces
as `ReconnectNeeded`, never as a crash.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from pydantic import SecretStr

SCOPE_PREFIX = "https://www.googleapis.com/auth/googlehealth."
SCOPES = tuple(
    f"{SCOPE_PREFIX}{name}.readonly"
    for name in ("activity_and_fitness", "health_metrics_and_measurements", "sleep", "nutrition")
)

AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class SyncError(RuntimeError):
    """Live sync cannot proceed; the message says what the user should do."""


class NotConfigured(SyncError):
    """No OAuth client is configured."""


class ReconnectNeeded(SyncError):
    """There is no usable sign-in: never connected, revoked, or expired."""


@dataclass(frozen=True)
class OAuthClient:
    client_id: str
    client_secret: str

    @classmethod
    def from_settings(cls, client_id: SecretStr | None, client_secret: SecretStr | None):
        values = [s.get_secret_value().strip() if s else "" for s in (client_id, client_secret)]
        if not all(values):
            raise NotConfigured(
                "Google sign-in is not configured: set FA_GOOGLE_CLIENT_ID and "
                "FA_GOOGLE_CLIENT_SECRET in .env (an OAuth client of type Desktop app)."
            )
        return cls(*values)

    def config(self) -> dict:
        return {
            "installed": {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "auth_uri": AUTH_URI,
                "token_uri": TOKEN_URI,
                "redirect_uris": ["http://localhost"],
            }
        }


def missing_scopes(granted: list[str] | tuple[str, ...] | None) -> list[str]:
    """Scopes we asked for that the user did not grant (Google lets them untick each one)."""
    return [scope for scope in SCOPES if scope not in set(granted or ())]


def save(credentials: Credentials, token_file: Path) -> None:
    """Writes the credentials so that only the current user can read them."""
    token_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(credentials.to_json())
    os.chmod(token_file, 0o600)  # also tighten a file that existed before


def connect(client: OAuthClient, token_file: Path, open_browser: bool = True) -> list[str]:
    """Runs the browser sign-in, stores the token, and returns any scopes that were not granted."""
    flow = InstalledAppFlow.from_client_config(client.config(), list(SCOPES))
    credentials = flow.run_local_server(
        port=0,
        open_browser=open_browser,
        access_type="offline",
        prompt="consent",  # always return a refresh token, even when signing in again
        authorization_prompt_message="Sign in to Google in your browser: {url}",
        success_message="Signed in. You can close this tab and go back to the terminal.",
    )
    save(credentials, token_file)
    return missing_scopes(credentials.granted_scopes or credentials.scopes)


def load(token_file: Path) -> Credentials:
    """Returns valid credentials, refreshing the access token if it expired."""
    if not token_file.exists():
        raise ReconnectNeeded("Not connected to Google Health: run `python -m app.sync connect`.")
    try:
        credentials = Credentials.from_authorized_user_info(json.loads(token_file.read_text()))
    except (ValueError, KeyError) as exc:  # includes a token saved without a refresh token
        message = "The saved Google sign-in is incomplete or unreadable; connect again."
        raise ReconnectNeeded(message) from exc

    if credentials.valid:
        return credentials
    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise ReconnectNeeded(
            "Google sign-in expired or was revoked (in Testing mode it lasts 7 days); "
            "run `python -m app.sync connect` again."
        ) from exc
    save(credentials, token_file)
    return credentials


def token_provider(token_file: Path) -> Callable[[], str]:
    """A function returning a current access token, renewing it when it expires."""
    credentials = load(token_file)

    def token() -> str:
        nonlocal credentials
        if not credentials.valid:
            credentials = load(token_file)
        return credentials.token

    return token


def disconnect(token_file: Path) -> bool:
    """Forgets the stored sign-in. Returns whether there was one."""
    if token_file.exists():
        token_file.unlink()
        return True
    return False
