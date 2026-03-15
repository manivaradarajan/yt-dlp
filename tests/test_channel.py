"""Tests for Channel.song_metadata() and Channel.url.

All tests are pure — strings in, dataclass out.  No network or file I/O.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from channel import Channel, normalize_initials
from config import DownloadConfig

# Shared channel instance reused across all tests in this file.
CH = Channel(handle="@CarnaticConnect", genre="Carnatic")


# ---------------------------------------------------------------------------
# song_metadata — non-chapter (standard video)
# ---------------------------------------------------------------------------


def test_non_chapter_song_title_is_album_title():
    """song_title equals album_title verbatim for a standard video."""
    md = CH.song_metadata("/path/to/file.mp3", "Madurai Mani Iyer - Concert")
    assert md.song_title == "Madurai Mani Iyer - Concert"


def test_non_chapter_album_title():
    """album_title equals the input title."""
    md = CH.song_metadata("/path/to/file.mp3", "Madurai Mani Iyer - Concert")
    assert md.album_title == "Madurai Mani Iyer - Concert"


def test_non_chapter_channel():
    """channel field equals the handle."""
    md = CH.song_metadata("/path/to/file.mp3", "Madurai Mani Iyer - Concert")
    assert md.channel == "@CarnaticConnect"


def test_non_chapter_genre():
    """genre field equals the channel's genre."""
    md = CH.song_metadata("/path/to/file.mp3", "Madurai Mani Iyer - Concert")
    assert md.genre == "Carnatic"


# ---------------------------------------------------------------------------
# song_metadata — chapter file
# ---------------------------------------------------------------------------


def test_chapter_song_title_strips_numeric_prefix():
    """is_chapter=True: song_title strips the leading track-number prefix."""
    md = CH.song_metadata("/path/to/01 Varnam.mp3", "Album Title", is_chapter=True)
    assert md.song_title == "Varnam"


def test_chapter_track_number_extracted():
    """is_chapter=True: track is the leading number from the filename stem."""
    md = CH.song_metadata("/path/to/01 Varnam.mp3", "Album Title", is_chapter=True)
    assert md.track == "01"


def test_chapter_album_title_unchanged():
    """is_chapter=True: album_title still equals the original video title."""
    md = CH.song_metadata("/path/to/01 Varnam.mp3", "Album Title", is_chapter=True)
    assert md.album_title == "Album Title"


# ---------------------------------------------------------------------------
# Artist extraction
# ---------------------------------------------------------------------------


def test_artist_default_pattern_matches():
    """Default r'^(.*?) -' pattern extracts artist from dash-separated title."""
    md = CH.song_metadata("/path/to/file.mp3", "Madurai Mani Iyer - Concert")
    assert md.artist == "Madurai Mani Iyer"


def test_artist_custom_pipe_pattern_matches():
    """Custom r'^(.*?) \\|' pattern extracts artist from pipe-separated title."""
    ch = Channel(handle="@Vaak", genre="Carnatic", artist_match=[r"^(.*?) \|"])
    md = ch.song_metadata("/path/to/file.mp3", "Ariyakudi | Aradhana")
    assert md.artist == "Ariyakudi"


def test_artist_fallback_to_second_pattern():
    """First pattern fails; second pattern matches the title."""
    ch = Channel(
        handle="@Mixed",
        genre="Carnatic",
        artist_match=[r"^(.*?) -", r"^(.*?) \|"],
    )
    md = ch.song_metadata("/path/to/file.mp3", "Ariyakudi | Aradhana")
    assert md.artist == "Ariyakudi"


def test_artist_no_match_returns_none():
    """No matching pattern → artist is None."""
    md = CH.song_metadata("/path/to/file.mp3", "NoMatchTitle")
    assert md.artist is None


# ---------------------------------------------------------------------------
# Year extraction
# ---------------------------------------------------------------------------


def test_year_single():
    """Single year in title → year == ['1954']."""
    md = CH.song_metadata("/path/to/file.mp3", "Concert 1954")
    assert md.year == ["1954"]


def test_year_multiple():
    """Multiple years in title → all are captured."""
    md = CH.song_metadata("/path/to/file.mp3", "Concert 1954 - Remastered 2010")
    assert md.year == ["1954", "2010"]


def test_year_none():
    """No year in title → year == []."""
    md = CH.song_metadata("/path/to/file.mp3", "Concert Title")
    assert md.year == []


# ---------------------------------------------------------------------------
# Channel.url
# ---------------------------------------------------------------------------


def test_channel_urls_derived_from_handle():
    """Default urls is a single-element list containing the /videos URL."""
    ch = Channel(handle="@Foo", genre="X")
    assert ch.urls == ["https://www.youtube.com/@Foo/videos"]


def test_channel_urls_uses_playlist_urls_when_set():
    """When playlist_urls is set, urls returns those instead of the /videos URL."""
    pl = ["https://www.youtube.com/playlist?list=PLaaa"]
    ch = Channel(handle="@Foo", genre="X", playlist_urls=pl)
    assert ch.urls == pl


# ---------------------------------------------------------------------------
# DownloadConfig.__post_init__ — channel coercion
# ---------------------------------------------------------------------------


def _make_cfg(**kwargs) -> DownloadConfig:
    """Return a minimal DownloadConfig with defaults for fields not under test."""
    defaults = dict(
        name="test",
        description="",
        genre="Carnatic",
        title_patterns=[],
        output="audio",
    )
    return DownloadConfig(**{**defaults, **kwargs})


def test_bare_string_coerced_to_channel():
    """A bare handle string is converted to a Channel with the config's genre."""
    cfg = _make_cfg(channels=["@Foo"])
    assert isinstance(cfg.channels[0], Channel)
    assert cfg.channels[0].handle == "@Foo"
    assert cfg.channels[0].genre == "Carnatic"


def test_explicit_channel_passed_through():
    """A Channel with an explicit genre is left unchanged by coercion."""
    ch = Channel(handle="@Bar", genre="Hindustani")
    cfg = _make_cfg(channels=[ch])
    assert cfg.channels[0].genre == "Hindustani"


def test_channel_without_genre_inherits_config_genre():
    """A Channel with genre=None gets the config's genre substituted in."""
    ch = Channel(handle="@Baz")  # genre defaults to None
    cfg = _make_cfg(channels=[ch])
    assert cfg.channels[0].genre == "Carnatic"


# ---------------------------------------------------------------------------
# normalize_initials — initials merging
# ---------------------------------------------------------------------------


def test_normalize_consecutive_two_initials():
    """Two consecutive single-letter tokens are merged into one."""
    assert normalize_initials("K V Narayanaswamy") == "KV Narayanaswamy"


def test_normalize_three_consecutive_initials():
    """Three consecutive single-letter tokens are all merged."""
    assert normalize_initials("K V N") == "KVN"


def test_normalize_single_initial_before_word():
    """A lone initial followed by a multi-letter word is left unchanged."""
    assert normalize_initials("M Balamuralikrishna") == "M Balamuralikrishna"


def test_normalize_already_merged():
    """A name with pre-merged initials is unchanged."""
    assert normalize_initials("KV Narayanaswamy") == "KV Narayanaswamy"


def test_normalize_no_initials():
    """A name with no single-letter tokens is returned unchanged."""
    assert (
        normalize_initials("Ariyakudi Ramanuja Iyengar") == "Ariyakudi Ramanuja Iyengar"
    )


def test_normalize_initials_applied_in_extract_artist():
    """_extract_artist returns a normalized name when the title has spaced initials."""
    ch = Channel(handle="@Test", genre="Carnatic")
    md = ch.song_metadata("/path/file.mp3", "K V Narayanaswamy - Concert 1970")
    assert md.artist == "KV Narayanaswamy"
