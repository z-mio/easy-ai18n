import os
import sys

from loguru import logger

logger.remove()
logger = logger.bind(module="easy_ai18n")
logger.add(
    sys.stderr,
    backtrace=True,
    level=os.getenv("I18N_LOG_LEVEL", "INFO"),
)
