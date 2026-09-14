import asyncio
import os
import sys

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scraper import main as run_scraper


def main() -> None:
    # Ensure this script runs in the repository context, even when the
    # workflow checks out the repo at a different runner location.
    os.chdir(REPO_ROOT)
    run_scraper()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as exc:
        raise exc
    except Exception as exc:
        print(f"run_scrape_with_tracking.py failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
