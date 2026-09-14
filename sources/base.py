from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SourceCollector(ABC):
    """Minimal contract for a source-specific collection adapter."""

    @abstractmethod
    def collect(self, run_id: str | None = None, **kwargs: Any) -> Any:
        """Collect raw source records for one collection run."""


class SourceParser(ABC):
    """Minimal contract for turning a source payload into structured events."""

    @abstractmethod
    def parse(self, raw_event: Any, **kwargs: Any) -> Any:
        """Parse the raw payload into a source-intermediate event/candidate."""


class SourceNormalizer(ABC):
    """Minimal contract for source-neutral normalization into the canonical model."""

    @abstractmethod
    def normalize(self, parsed: Any, **kwargs: Any) -> Any:
        """Return a source-neutral normalized listing object."""
