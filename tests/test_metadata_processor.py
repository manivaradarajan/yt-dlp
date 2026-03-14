"""Tests for metadata_processor helpers.

All tests are pure — no real file I/O.
"""

import pathlib
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from metadata_processor import SetFileMetadata, _normalize_handle


def test_normalize_handle_adds_at_prefix():
    """Handle without @ gets the prefix added."""
    assert _normalize_handle("CarnaticConnect") == "@CarnaticConnect"


def test_normalize_handle_keeps_existing_prefix():
    """Handle already with @ is returned unchanged."""
    assert _normalize_handle("@CarnaticConnect") == "@CarnaticConnect"


def test_normalize_handle_empty_string():
    """Empty string is returned unchanged."""
    assert _normalize_handle("") == ""


# ---------------------------------------------------------------------------
# SetFileMetadata — chapters=None guard
# ---------------------------------------------------------------------------


def _make_mock_channel(handle: str = "@TestChannel"):
    """Return a Channel mock with a no-op song_metadata method."""
    ch = MagicMock()
    ch.handle = handle
    ch.song_metadata.return_value = MagicMock()
    return ch


def test_set_file_metadata_chapters_none():
    """chapters=None does not raise TypeError when a handler is registered."""
    ch = _make_mock_channel()
    pp = SetFileMetadata(channels=[ch])
    info = {
        "ext": "mp3",
        "filepath": "/fake/song.mp3",
        "title": "Test Song",
        "uploader_id": "@TestChannel",
        "chapters": None,
    }
    with patch.object(pp, "_set_song_metadata"):
        files_to_delete, _ = pp.run(info)
    assert files_to_delete == []


def test_set_file_metadata_chapters_absent():
    """Missing chapters key does not raise TypeError when a handler is registered."""
    ch = _make_mock_channel()
    pp = SetFileMetadata(channels=[ch])
    info = {
        "ext": "mp3",
        "filepath": "/fake/song.mp3",
        "title": "Test Song",
        "uploader_id": "@TestChannel",
    }
    with patch.object(pp, "_set_song_metadata"):
        files_to_delete, _ = pp.run(info)
    assert files_to_delete == []
