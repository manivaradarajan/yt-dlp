"""Tests for pure helper functions in download.py.

Imports functions directly — no yt-dlp network calls or file I/O.
"""

import copy
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest

from channel import Channel
from clipping import parse_time
from download import (
    OPTIONS,
    configure_video_mode,
    load_configs,
    make_title_filter,
    resolve_configs,
    video_format,
)
from postprocessors import (
    DeleteUnsplitAudio,
    InjectArtistMetadata,
    WriteChapterPlaylist,
    WriteDescriptionAsTxt,
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
# WriteDescriptionAsTxt — txt placement
# ---------------------------------------------------------------------------


def test_txt_path_no_chapters_is_alongside_audio():
    """Without chapters the .txt is next to the audio file."""
    pp = WriteDescriptionAsTxt()
    result = pp._txt_path("/out/Artist/Concert.mp3", chapters=None)
    assert result == "/out/Artist/Concert.txt"


def test_txt_path_with_chapters_goes_inside_album_dir():
    """With chapter filepaths the .txt lands inside the chapter directory."""
    pp = WriteDescriptionAsTxt()
    chapters = [{"filepath": "/out/Artist/Concert/01 Track.mp3"}]
    result = pp._txt_path("/out/Artist/Concert.mp3", chapters=chapters)
    assert result == "/out/Artist/Concert/Concert.txt"


def test_txt_path_chapters_without_filepath_treated_as_no_split():
    """Chapters list whose entries lack filepath is treated like no split."""
    pp = WriteDescriptionAsTxt()
    chapters = [{"title": "Intro"}]  # no "filepath" key
    result = pp._txt_path("/out/Artist/Concert.mp3", chapters=chapters)
    assert result == "/out/Artist/Concert.txt"


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


# ---------------------------------------------------------------------------
# InjectArtistMetadata — channel lookup and artist extraction
# ---------------------------------------------------------------------------

_CHANNEL = Channel(handle="@TestChannel", genre="Carnatic")
_CHANNEL_MAP = {"@TestChannel": _CHANNEL}


def _make_inject_pp(
    artist_aliases: dict | None = None, verbose: bool = False
) -> InjectArtistMetadata:
    """Return an InjectArtistMetadata instance with a single test channel."""
    return InjectArtistMetadata(
        _CHANNEL_MAP, artist_aliases=artist_aliases, verbose=verbose
    )


def test_inject_artist_via_uploader_id():
    """Artist is extracted when uploader_id matches a registered handle."""
    pp = _make_inject_pp()
    _, info = pp.run(
        {"title": "Ariyakudi - Concert 1950", "uploader_id": "@TestChannel"}
    )
    assert info["artist"] == "Ariyakudi"


def test_inject_artist_uploader_id_missing_at():
    """uploader_id without leading @ is normalised and still resolves."""
    pp = _make_inject_pp()
    _, info = pp.run(
        {"title": "Ariyakudi - Concert 1950", "uploader_id": "TestChannel"}
    )
    assert info["artist"] == "Ariyakudi"


def test_inject_artist_via_channel_url_fallback():
    """Artist is extracted via channel_url when uploader_id is a UC-style ID."""
    pp = _make_inject_pp()
    _, info = pp.run(
        {
            "title": "Ariyakudi - Concert 1950",
            "uploader_id": "UCxxxxxxxxxxxxxxxxxxxxxx",
            "channel_url": "https://www.youtube.com/@TestChannel",
            "uploader": "Test Channel Display Name",
        }
    )
    assert info["artist"] == "Ariyakudi"


def test_inject_artist_no_channel_falls_back_to_uploader():
    """Falls back to the uploader display name when no handler is registered."""
    pp = _make_inject_pp()
    _, info = pp.run(
        {
            "title": "Some Video",
            "uploader_id": "@UnknownChannel",
            "channel_url": "https://www.youtube.com/@UnknownChannel",
            "uploader": "Unknown Channel",
        }
    )
    assert info["artist"] == "Unknown Channel"


def test_inject_artist_pattern_no_match_falls_back_to_uploader():
    """Falls back to uploader when channel is found but title doesn't match pattern."""
    pp = _make_inject_pp()
    # Default pattern r"^(.*?) -" won't match a title with no " - " separator.
    _, info = pp.run(
        {
            "title": "NoSeparatorHere",
            "uploader_id": "@TestChannel",
            "uploader": "Test Channel Display Name",
        }
    )
    assert info["artist"] == "Test Channel Display Name"


def test_inject_artist_verbose_logs_success(capsys):
    """Verbose mode prints an [artist] line on successful extraction."""
    pp = _make_inject_pp(verbose=True)
    pp.run({"title": "Ariyakudi - Concert 1950", "uploader_id": "@TestChannel"})
    assert "[artist]" in capsys.readouterr().out


def test_inject_artist_verbose_logs_fallback(capsys):
    """Verbose mode prints an [artist] line when falling back to uploader."""
    pp = _make_inject_pp(verbose=True)
    pp.run(
        {
            "title": "Some Video",
            "uploader_id": "@UnknownChannel",
            "uploader": "Unknown Channel",
        }
    )
    assert "[artist]" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# InjectArtistMetadata — artist alias application
# ---------------------------------------------------------------------------


def test_inject_artist_alias_applied():
    """Alias map entry is used when the extracted artist matches a key."""
    pp = _make_inject_pp(artist_aliases={"Ariyakudi": "Ariyakudi Ramanuja Iyengar"})
    _, info = pp.run(
        {"title": "Ariyakudi - Concert 1950", "uploader_id": "@TestChannel"}
    )
    assert info["artist"] == "Ariyakudi Ramanuja Iyengar"


def test_inject_artist_alias_not_applied_when_no_match():
    """Artist is returned unchanged when it is not present in the alias map."""
    pp = _make_inject_pp(artist_aliases={"Someone Else": "Canonical Name"})
    _, info = pp.run(
        {"title": "Ariyakudi - Concert 1950", "uploader_id": "@TestChannel"}
    )
    assert info["artist"] == "Ariyakudi"


def test_inject_artist_alias_applied_on_fallback():
    """Alias is applied even when the artist comes from the uploader fallback."""
    pp = _make_inject_pp(artist_aliases={"Unknown Channel": "Canonical Name"})
    _, info = pp.run(
        {
            "title": "NoSeparatorHere",
            "uploader_id": "@TestChannel",
            "uploader": "Unknown Channel",
        }
    )
    assert info["artist"] == "Canonical Name"
