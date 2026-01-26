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
    config.addinivalue_line(
        "markers",
        "requires_gh: marks tests that require the gh CLI tool",
    )


def pytest_collection_modifyitems(config, items):
    """Skip tests that require external tools if not installed."""
    gmap_available = shutil.which("gmap") is not None
    gh_available = shutil.which("gh") is not None

    skip_gmap = pytest.mark.skip(reason="gmap CLI not installed")
    skip_gh = pytest.mark.skip(reason="gh CLI not installed")

    for item in items:
        if "requires_gmap" in item.keywords and not gmap_available:
            item.add_marker(skip_gmap)
        if "requires_gh" in item.keywords and not gh_available:
            item.add_marker(skip_gh)
