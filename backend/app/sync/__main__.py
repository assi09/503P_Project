"""Command line for the Google Health sign-in: `python -m app.sync <command>`.

Run from the repository root with the virtual environment active. Nothing here prints tokens or
health values; `check` only reports whether each kind of data can be read.
"""

import argparse
import sys

import httpx2

from app.config import settings
from app.sync.google_auth import (
    OAuthClient,
    SyncError,
    connect,
    disconnect,
    load,
    missing_scopes,
)

API = "https://health.googleapis.com/v4/users/me/dataTypes"

# One data type per scope, to confirm each grant works end to end.
CHECKS = {
    "activity_and_fitness": "steps",
    "health_metrics_and_measurements": "daily-resting-heart-rate",
    "sleep": "sleep",
    "nutrition": "nutrition-log",
}


def _connect() -> int:
    client = OAuthClient.from_settings(settings.google_client_id, settings.google_client_secret)
    missing = connect(client, settings.google_token_file)
    print(f"Connected. Sign-in saved to {settings.google_token_file}.")
    if missing:
        print("Not granted (those data types will be skipped):")
        for scope in missing:
            print(f"  - {scope}")
    return 0


def _status() -> int:
    credentials = load(settings.google_token_file)
    print("Connected.")
    print(f"Access token valid until {credentials.expiry:%Y-%m-%d %H:%M} UTC.")
    for scope in missing_scopes(credentials.scopes):
        print(f"Not granted: {scope}")
    return 0


def _check() -> int:
    credentials = load(settings.google_token_file)
    headers = {"Authorization": f"Bearer {credentials.token}"}
    failures = 0
    with httpx2.Client(timeout=20) as http:
        for scope, data_type in CHECKS.items():
            url = f"{API}/{data_type}/dataPoints"
            response = http.get(url, params={"pageSize": 1}, headers=headers)
            if response.is_success:
                count = len(response.json().get("dataPoints", []))
                print(f"{data_type:<26} ok   ({count} point returned)")
            else:
                failures += 1
                reason = response.json().get("error", {}).get("status", response.reason_phrase)
                print(f"{data_type:<26} {response.status_code}  {reason}  (scope: {scope})")
    return 1 if failures else 0


def _disconnect() -> int:
    removed = disconnect(settings.google_token_file)
    print("Signed out." if removed else "Was not connected.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.sync")
    commands = {"connect": _connect, "status": _status, "check": _check, "disconnect": _disconnect}
    parser.add_argument("command", choices=commands)
    args = parser.parse_args(argv)
    try:
        return commands[args.command]()
    except SyncError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
