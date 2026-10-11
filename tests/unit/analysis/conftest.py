"""Fixtures shared by the analysis tests."""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def head_tree():
    """Stand in for the HEAD tree and commit of the fake repositories these tests analyze."""
    with (
        patch("black_box_unlock.git.history.head_paths", return_value=frozenset()) as mock,
        patch("black_box_unlock.analysis.head_oid", return_value="a" * 40),
        patch("black_box_unlock.analysis.is_shallow", return_value=False),
    ):
        yield mock
