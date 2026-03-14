"""Tests for _normalize_handle in metadata_processor.

All tests are pure — string in, string out.  No file I/O.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from metadata_processor import _normalize_handle


def test_normalize_handle_adds_at_prefix():
    """Handle without @ gets the prefix added."""
    assert _normalize_handle("CarnaticConnect") == "@CarnaticConnect"


def test_normalize_handle_keeps_existing_prefix():
    """Handle already with @ is returned unchanged."""
    assert _normalize_handle("@CarnaticConnect") == "@CarnaticConnect"


def test_normalize_handle_empty_string():
    """Empty string is returned unchanged."""
    assert _normalize_handle("") == ""
