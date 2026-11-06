# studyguard/vision/results.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DetectionResult:
    name: str
    detected: bool
    confidence: float
    event_type: str | None = None
    severity: str = "info"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def state(self) -> str:
        return str(self.metadata.get("state", "UNKNOWN"))

    @property
    def label(self) -> str:
        return str(self.metadata.get("label", self.name.upper()))

    @property
    def score(self) -> float:
        value = self.metadata.get("score", self.confidence)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(self.confidence)

    @property
    def is_warning(self) -> bool:
        return self.severity in {"warning", "danger", "fatigue"}

    def with_metadata(self, **values: Any) -> DetectionResult:
        metadata = dict(self.metadata)
        metadata.update(values)
        return DetectionResult(
            name=self.name,
            detected=self.detected,
            confidence=self.confidence,
            event_type=self.event_type,
            severity=self.severity,
            metadata=metadata,
        )