"""Command line for Google Health live data: `python -m app.sync <command>`.

Run from the repository root with the virtual environment active. Nothing here prints tokens or
health values: `check` reports whether each kind of data can be read, and `compare` how closely
the API reproduces a Takeout export, in aggregate.
"""

import argparse
import sys
from datetime import timedelta

import httpx2

from app.config import settings
from app.ingest.takeout import load_daily as takeout_daily
from app.sync.client import HealthClient
from app.sync.compare import agreement
from app.sync.daily import load_daily
from app.sync.google_auth import (
    OAuthClient,
    SyncError,
    connect,
    disconnect,
    load,
    missing_scopes,
    token_provider,
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


def _compare(export: str) -> int:
    reference = takeout_daily(export, settings.timezone).frame
    start, end = reference.index.min().date(), reference.index.max().date() + timedelta(days=1)
    health = HealthClient(token_provider(settings.google_token_file))
    live = load_daily(health, start, end)
    print(f"Google Health API vs {export}, {start} to {end - timedelta(days=1)}")
    table = agreement(live.frame, reference)
    for name in ("within_1pct", "within_5pct"):
        table[name] = table[name].map("{:.0%}".format)
    print(table.to_string(float_format="{:.2f}".format))
    print(f"Not available from the API: {', '.join(live.missing)}")
    return 0


def _disconnect() -> int:
    removed = disconnect(settings.google_token_file)
    print("Signed out." if removed else "Was not connected.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.sync")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("connect", "status", "check", "disconnect"):
        commands.add_parser(name)
    compare = commands.add_parser("compare", help="check the API against a Takeout export")
    compare.add_argument("--export", required=True, help="an extracted Takeout export")
    args = parser.parse_args(argv)
    simple = {"connect": _connect, "status": _status, "check": _check, "disconnect": _disconnect}
    try:
        if args.command == "compare":
            return _compare(args.export)
        return simple[args.command]()
    except SyncError as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
