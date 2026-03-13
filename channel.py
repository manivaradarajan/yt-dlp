"""Channel definitions for per-channel metadata extraction.

Each Channel subclass knows how to parse a video title and filename into a
SongMetadata dataclass, which is used by SetFileMetadata to write ID3 tags.
"""
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass


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


class Channel(ABC):
    """Abstract base class for a YouTube channel with metadata extraction logic."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def song_metadata(self, filepath: str, album_title: str, is_chapter: bool = False) -> SongMetadata:
        """Extract song metadata from a downloaded file path and video title.

        Args:
            filepath: Path to the downloaded audio file.
            album_title: The YouTube video title, used as the album name.
            is_chapter: True if this file is a chapter split from a larger video.

        Returns:
            A SongMetadata instance populated from the filename and title.
        """


class CarnaticChannel(Channel):
    """Channel handler for Carnatic classical music channels.

    Parses artist, track number, and year from the video title and filename
    using configurable regex patterns.
    """

    # Matches leading numbers, spaces, and dots (e.g. chapter prefixes like "01 ").
    _NUMERIC_PREFIX = r"^[\s0-9\. ]+"
    # Track number is a leading integer followed by a space.
    _TRACK_PREFIX = r"^(\d+) "
    # Default: artist is everything before the first " -" in the title.
    # Example: "Madurai Mani Iyer - Wedding Concert, 1950's"
    _DEFAULT_ARTIST_MATCH = r"^(.*?) -"

    GENRE = "Carnatic"

    def __init__(self, channel: str, main_artist_match: str = None):
        """Initialise the channel, optionally overriding the artist regex.

        Args:
            channel: The YouTube channel name (must match yt-dlp's channel field).
            main_artist_match: Regex with one capture group for the artist name.
                Defaults to matching everything before " -" in the title.
        """
        super().__init__(channel)
        self._main_artist_match = main_artist_match or self._DEFAULT_ARTIST_MATCH

    def song_metadata(self, filepath: str, album_title: str, is_chapter: bool = False) -> SongMetadata:
        """Extract song metadata from a downloaded file path and video title.

        Args:
            filepath: Path to the downloaded audio file.
            album_title: The YouTube video title, used as the album name.
            is_chapter: True if this file is a chapter split from a larger video.

        Returns:
            A SongMetadata instance populated from the filename and title.
        """
        filename_no_ext = os.path.splitext(os.path.basename(filepath))[0]

        # For chapters, strip the leading track-number prefix to get the song title.
        song_title = (
            re.sub(self._NUMERIC_PREFIX, "", filename_no_ext) if is_chapter else album_title
        )

        artist_match = re.match(self._main_artist_match, album_title)
        artist = artist_match.group(1) if artist_match else None

        year = re.findall(r"((?:19|20)\d\d)", album_title)

        track_match = re.match(self._TRACK_PREFIX, filename_no_ext)
        track = track_match.group(1) if track_match else None

        return SongMetadata(
            artist=artist,
            album_title=album_title,
            channel=self.name,
            song_title=song_title,
            track=track,
            year=year,
            genre=CarnaticChannel.GENRE,
        )
