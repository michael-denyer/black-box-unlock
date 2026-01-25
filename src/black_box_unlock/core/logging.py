"""Logging configuration for black-box-unlock."""

import sys

from loguru import logger


def configure_logging(verbose: bool = False) -> None:
    """Configure loguru for CLI usage.

    Args:
        verbose: If True, log INFO and above. If False, log WARNING and above.
    """
    logger.remove()

    level = "INFO" if verbose else "WARNING"

    logger.add(
        sys.stderr,
        level=level,
        format="<level>{level: <8}</level> | {message}",
        colorize=True,
    )
