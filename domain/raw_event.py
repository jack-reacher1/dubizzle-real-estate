from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RawSourceEvent:
    """Minimal raw event abstraction for future multi-source ingestion.

    It is intentionally source-agnostic and holds the metadata needed to
    remember where the payload came from, when it was collected, and under
    which collection run it was observed.
    """

    source: str
    source_id: str
    source_url: Optional[str] = None
    raw_payload: Any = None
    collected_at: Optional[str] = None
    collection_run_id: Optional[str] = None
