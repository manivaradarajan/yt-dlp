"""Channel definitions and download configuration dataclasses.

``Channel`` encapsulates a YouTube channel's identity and ID3 tag extraction
logic.  ``DownloadConfig`` bundles a set of channels with title-filter patterns
and an output mode (audio vs. video) into a self-contained configuration.
``SongMetadata`` holds the extracted ID3 tag fields written by
``SetFileMetadata``.
"""

import os
import re
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(frozen=True)
class SongMetadata:
    """Metadata for an audio file extracted from a YouTube video."""

    album_title: str
    channel: str
    song_title: str
    artist: str = None
    track: str = None
    year: list = None
    genre: str = None


@dataclass
class Channel:
    """A YouTube channel: where to download from and how to extract ID3 metadata.

    The handle (e.g. ``@CarnaticConnect``) is the primary identifier — stable,
    already unique, and the playlist URL is fully derived from it.
    """

    handle: str
    """YouTube channel handle, e.g. ``@CarnaticConnect``."""

    genre: str | None = None
    """ID3 genre tag value for all tracks from this channel.

    May be ``None`` when the channel is defined inline inside a ``DownloadConfig``
    that declares a config-level ``genre`` — ``DownloadConfig.__post_init__``
    fills this in automatically.
    """

    artist_match: list[str] = field(default_factory=lambda: [r"^(.*?) -"])
    """Regexes tried in order to extract the artist name from the video title.

    Each pattern must have exactly one capture group — the captured text
    becomes the artist.  Patterns are tried in order; the first match wins.
    If none match, artist is left blank.

    Examples::

        title "Madurai Mani Iyer - Wedding Concert, 1950's"
        pattern r"^(.*?) -"  →  captures "Madurai Mani Iyer"

        title "Ariyakudi Ramanuja Iyengar | Thyagaraja Aradhana"
        pattern r"^(.*?) \\|"  →  captures "Ariyakudi Ramanuja Iyengar"

    Use a list when a single channel uses varied title formats across its videos.
    """

    playlist_urls: list[str] = field(default_factory=list)
    """Explicit playlist URLs to download instead of the channel's ``/videos`` page.

    When non-empty, these URLs are used verbatim and the default ``/videos`` URL
    is ignored.  Useful for downloading specific playlists rather than the full
    channel upload history.

    Example::

        Channel(
            handle="@MyChannel",
            playlist_urls=[
                "https://www.youtube.com/playlist?list=PLaaa",
                "https://www.youtube.com/playlist?list=PLbbb",
            ],
        )
    """

    # Class-level constants excluded from __init__ / __repr__.
    _NUMERIC_PREFIX: ClassVar[str] = r"^[\s0-9\. ]+"
    """Matches leading numbers, spaces, and dots (e.g. chapter prefix "01 ")."""

    _TRACK_PREFIX: ClassVar[str] = r"^(\d+) "
    """Matches a leading track number followed by a space."""

    @property
    def urls(self) -> list[str]:
        """Return the URLs to download for this channel.

        If ``playlist_urls`` is set, those are returned verbatim.
        Otherwise returns the channel's ``/videos`` page URL derived from the handle.

        Example: ``@CarnaticConnect`` → ``["https://www.youtube.com/@CarnaticConnect/videos"]``
        """
        if self.playlist_urls:
            return self.playlist_urls
        return [f"https://www.youtube.com/{self.handle}/videos"]

    def _extract_artist(self, album_title: str) -> str | None:
        """Try each ``artist_match`` pattern and return the first capture group.

        Args:
            album_title: The YouTube video title to extract the artist name from.

        Returns:
            The matched artist name, or ``None`` if no pattern matched.
        """
        for pattern in self.artist_match:
            m = re.match(pattern, album_title)
            if m:
                return m.group(1)
        return None

    def song_metadata(
        self, filepath: str, album_title: str, is_chapter: bool = False
    ) -> SongMetadata:
        """Extract ``SongMetadata`` from a filepath and video title.

        Args:
            filepath: Path to the downloaded audio file.
            album_title: The YouTube video title, used as the album name.
            is_chapter: True if this file is a chapter split from a larger video.

        Returns:
            A ``SongMetadata`` instance populated from the filename and title.
        """
        filename_no_ext = os.path.splitext(os.path.basename(filepath))[0]

        # For chapters, strip the leading track-number prefix to get the song title.
        song_title = (
            re.sub(self._NUMERIC_PREFIX, "", filename_no_ext)
            if is_chapter
            else album_title
        )

        artist = self._extract_artist(album_title)
        year = re.findall(r"((?:19|20)\d\d)", album_title)

        track_match = re.match(self._TRACK_PREFIX, filename_no_ext)
        track = track_match.group(1) if track_match else None

        return SongMetadata(
            artist=artist,
            album_title=album_title,
            channel=self.handle,
            song_title=song_title,
            track=track,
            year=year,
            genre=self.genre,
        )


