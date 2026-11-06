from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from studyguard.vision.results import DetectionResult


class BaseDetector(ABC):
    name = "base"

    @abstractmethod
    def process(self, frame: Any, timestamp: float) -> DetectionResult:
        raise NotImplementedError
