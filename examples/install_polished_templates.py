"""Install the bundled modern templates into a running notification service.

This intentionally overwrites templates with the same event names. Review the
templates in service/app/default_templates.py before using --replace.
"""
import argparse
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "service"))
from app.default_templates import DEFAULT_TEMPLATES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="overwrite templates with the bundled designs")
    args = parser.parse_args()
    if not args.replace:
        parser.error("refusing to overwrite templates; re-run with --replace after reviewing the source")

    base_url = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8000").rstrip("/")
    with httpx.Client(timeout=10) as client:
        for event, template in DEFAULT_TEMPLATES.items():
            response = client.put(f"{base_url}/templates/{event}", json=template)
            response.raise_for_status()
            print(f"Installed {event}")


if __name__ == "__main__":
    main()
