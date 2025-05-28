import os
import sys
from loguru import logger

logger = logger.bind(module="easy_ai18n")

_log_level = os.getenv("I18N_LOG_LEVEL", "INFO").upper()
if _log_level == "DEBUG":
    logger.add(
        sys.stderr,
        level="DEBUG",
        backtrace=True,
        filter=lambda record: record["extra"].get("module") == "easy_ai18n",
        enqueue=True,
    )
