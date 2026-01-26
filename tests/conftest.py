"""Shared test fixtures."""

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    """Return the repository root path."""
    return Path(__file__).parent.parent


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "requires_gmap: marks tests that require the gmap CLI tool",
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests that require gmap if it's not installed."""
    gmap_available = shutil.which("gmap") is not None
    if gmap_available:
        return

    skip_gmap = pytest.mark.skip(reason="gmap CLI not installed")
    for item in items:
        if "requires_gmap" in item.keywords:
            item.add_marker(skip_gmap)
