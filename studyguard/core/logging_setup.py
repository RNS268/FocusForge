from __future__ import annotations

import logging
from pathlib import Path


def setup_logging() -> None:
    log_dir = Path.home() / "StudyGuardAI" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "studyguard.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
