"""Unit tests for logging configuration."""

from io import StringIO
from unittest.mock import patch

from loguru import logger

from black_box_unlock.core.logging import configure_logging


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_default_level_is_warning(self):
        """Default configuration logs WARNING and above to stderr."""
        output = StringIO()

        with patch("sys.stderr", output):
            configure_logging(verbose=False)
            logger.debug("debug message")
            logger.info("info message")
            logger.warning("warning message")

        result = output.getvalue()

        assert "debug" not in result.lower()
        assert "info" not in result.lower()
        assert "warning" in result.lower()

    def test_verbose_enables_info_level(self):
        """Verbose mode logs INFO and above to stderr."""
        output = StringIO()

        with patch("sys.stderr", output):
            configure_logging(verbose=True)
            logger.debug("debug message")
            logger.info("info message")
            logger.warning("warning message")

        result = output.getvalue()

        assert "debug" not in result.lower()
        assert "info" in result.lower()
        assert "warning" in result.lower()
