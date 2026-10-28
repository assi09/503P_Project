"""`python -m app.reminders deliver`: send the reminders due now, once, and print the counts."""

import argparse

from app.reminders.loop import run_once


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.reminders")
    parser.add_argument("command", choices=["deliver"])
    parser.parse_args()
    run_once()
    print("Done; counts are in the log.")


if __name__ == "__main__":
    main()
