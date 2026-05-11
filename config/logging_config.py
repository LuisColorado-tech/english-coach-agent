"""
Logging configuration with loguru.
File rotation and console output.
"""

import sys
from pathlib import Path
from loguru import logger

from config.settings import LOG_LEVEL, LOG_ROTATION, LOG_RETENTION, LOGS_DIR


def setup_logging():
    logger.remove()

    # Console sink
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level=LOG_LEVEL,
        colorize=True,
    )

    # File sink with rotation
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "eca.log"

    logger.add(
        log_file,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation=LOG_ROTATION,
        retention=LOG_RETENTION,
        compression="zip",
        encoding="utf-8",
    )

    return logger
