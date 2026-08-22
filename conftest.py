import sys
from pathlib import Path

# Ensure repository root is on sys.path so top-level modules (app, services, scraper)
# can be imported during pytest collection without requiring PYTHONPATH.
_repo_root = Path(__file__).resolve().parent
_repo_root_str = str(_repo_root)
if _repo_root_str not in sys.path:
    sys.path.insert(0, _repo_root_str)
