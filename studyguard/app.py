# studyguard/app.py

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from studyguard.core.config import ConfigManager
from studyguard.core.logging_setup import setup_logging
from studyguard.database.db import Database


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        config_path = Path("config/default_config.json")
        config = ConfigManager(config_path)

        db = Database(config.user_data_dir / "studyguard.sqlite3")
        db.initialize()

        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from studyguard.ui.main_window import MainWindow
        from studyguard.ui.splash import SplashScreen

    except Exception as exc:
        logger.exception("Unable to initialize StudyGuard AI")
        print("StudyGuard AI failed to initialize.")
        print(f"Error: {exc}")
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("StudyGuard AI")
    app.setApplicationDisplayName("StudyGuard AI")
    app.setOrganizationName("StudyGuard")

    try:
        app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass

    splash = SplashScreen()
    splash.show()
    app.processEvents()

    time.sleep(0.8)

    try:
        window = MainWindow(config=config, database=db)
        window.show()
        splash.close()
    except Exception as exc:
        logger.exception("Unable to create main window")
        splash.close()
        print("StudyGuard AI failed to start the main window.")
        print(f"Error: {exc}")
        return 1

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())