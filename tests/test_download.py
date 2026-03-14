"""Tests for pure helper functions in download.py.

Imports functions directly — no yt-dlp network calls or file I/O.
"""

import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest

from download import (
    OPTIONS,
    DeleteUnsplitAudio,
    WriteChapterPlaylist,
    configure_video_mode,
    load_configs,
    make_title_filter,
    parse_time,
    resolve_configs,
    video_format,
)

# ---------------------------------------------------------------------------
# parse_time
# ---------------------------------------------------------------------------


def test_parse_time_hhmmss():
    assert parse_time("1:30:00") == 5400.0


def test_parse_time_mmss():
    assert parse_time("45:00") == 2700.0


def test_parse_time_seconds():
    assert parse_time("90") == 90.0


# ---------------------------------------------------------------------------
# make_title_filter
# ---------------------------------------------------------------------------


def test_title_filter_matching_returns_none():
    """Title matching any pattern returns None (allow the video)."""
    f = make_title_filter([r"Ariyakudi", r"Madurai Mani"])
    assert f({"title": "Ariyakudi Ramanuja Iyengar Concert"}) is None


def test_title_filter_non_matching_returns_string():
    """Title matching no pattern returns a non-None string (skip the video)."""
    f = make_title_filter([r"Ariyakudi", r"Madurai Mani"])
    result = f({"title": "Some Random Video"})
    assert result is not None
    assert isinstance(result, str)


def test_title_filter_case_sensitive():
    """Filter is case-sensitive: uppercase pattern does not match lowercase title."""
    f = make_title_filter([r"Ariyakudi"])
    assert f({"title": "ariyakudi"}) is not None


# ---------------------------------------------------------------------------
# video_format
# ---------------------------------------------------------------------------


def test_video_format_no_height():
    assert video_format(None) == "bestvideo+bestaudio/best"


def test_video_format_with_height():
    assert (
        video_format("1080") == "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
    )


# ---------------------------------------------------------------------------
# configure_video_mode
# ---------------------------------------------------------------------------


def _make_options() -> dict:
    """Return a deep copy of the global OPTIONS dict for isolated testing."""
    return copy.deepcopy(OPTIONS)


def test_configure_video_mode_removes_extract_audio():
    """FFmpegExtractAudio postprocessor is removed."""
    opts = _make_options()
    configure_video_mode(opts)
    keys = [pp["key"] for pp in opts["postprocessors"]]
    assert "FFmpegExtractAudio" not in keys


def test_configure_video_mode_removes_final_ext():
    """final_ext key is removed from options."""
    opts = _make_options()
    configure_video_mode(opts)
    assert "final_ext" not in opts


def test_configure_video_mode_format_no_height():
    """format is set to best available when max_height is None."""
    opts = _make_options()
    configure_video_mode(opts, max_height=None)
    assert opts["format"] == "bestvideo+bestaudio/best"


def test_configure_video_mode_format_with_height():
    """format is capped at the given height."""
    opts = _make_options()
    configure_video_mode(opts, max_height="1080")
    assert opts["format"] == "bestvideo[height<=1080]+bestaudio/best[height<=1080]"


# ---------------------------------------------------------------------------
# load_configs
# ---------------------------------------------------------------------------


def test_load_configs_contains_carnatic():
    """Returned dict contains the 'carnatic' key."""
    configs = load_configs()
    assert "carnatic" in configs


def test_load_configs_carnatic_output_is_audio():
    configs = load_configs()
    assert configs["carnatic"].output == "audio"


def test_load_configs_carnatic_has_channels():
    configs = load_configs()
    assert len(configs["carnatic"].channels) > 0


# ---------------------------------------------------------------------------
# resolve_configs
# ---------------------------------------------------------------------------


def test_resolve_configs_single():
    """Single name resolves to a list of length 1."""
    result = resolve_configs("carnatic")
    assert len(result) == 1
    assert result[0].name == "carnatic"


def test_resolve_configs_unknown_raises_system_exit():
    """Unknown config name raises SystemExit."""
    with pytest.raises(SystemExit):
        resolve_configs("nonexistent_config")


def test_resolve_configs_duplicate_allowed():
    """Comma-separated duplicate names each produce an entry."""
    result = resolve_configs("carnatic,carnatic")
    assert len(result) == 2


# ---------------------------------------------------------------------------
# WriteChapterPlaylist — chapters=None guard
# ---------------------------------------------------------------------------

_BASE_INFO = {"filepath": "/tmp/x.mp3"}


def test_write_chapter_playlist_chapters_none():
    """chapters=None does not raise TypeError; no files scheduled for deletion."""
    pp = WriteChapterPlaylist()
    files_to_delete, _ = pp.run({**_BASE_INFO, "chapters": None})
    assert files_to_delete == []


def test_write_chapter_playlist_chapters_absent():
    """Missing chapters key does not raise TypeError."""
    pp = WriteChapterPlaylist()
    files_to_delete, _ = pp.run({**_BASE_INFO})
    assert files_to_delete == []


# ---------------------------------------------------------------------------
# DeleteUnsplitAudio — chapters=None guard
# ---------------------------------------------------------------------------


def test_delete_unsplit_audio_chapters_none():
    """chapters=None does not raise TypeError; no files scheduled for deletion."""
    pp = DeleteUnsplitAudio()
    files_to_delete, _ = pp.run({**_BASE_INFO, "chapters": None})
    assert files_to_delete == []


def test_delete_unsplit_audio_chapters_absent():
    """Missing chapters key does not raise TypeError."""
    pp = DeleteUnsplitAudio()
    files_to_delete, _ = pp.run({**_BASE_INFO})
    assert files_to_delete == []
