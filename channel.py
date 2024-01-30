import abc
import os
import re
from abc import abstractmethod
from dataclasses import dataclass

import mutagen
from mutagen import id3, mp3


@dataclass(frozen=True)
class SongMetadata:
    """Dataclass representing metadata for an audio file extracted from a YouTube video."""

    album_title: str
    channel: str
    song_title: str
    artist: str = None
    track: int = None
    year: int = None
    genre: str = None


class Channel(abc.ABC):
    # The name of the channel.
    name = None

    def __init__(self, channel_name):
        self.name = channel_name

    @abstractmethod
    def song_metadata(self, filepath, album_title, is_chapter=False):
        pass


class CarnaticChannel(Channel):
    # Matches all numbers, spaces and the '.' at the beginning of a string.
    _NUMERIC_PREFIX = r"^[\s0-9\. ]+"
    # The track is always at the beginning of the string, before a space.
    _TRACK_PREFIX = r"^(\d+) "

    # The main artist is always at the beginning of the string before "-".
    # Example: "Madurai Mani Iyer - Wedding Concert, 1950’s"
    _main_artist_match = r"^(.*?) -"

    GENRE = "Carnatic"

    def __init__(self, channel, **kwargs):
        super(CarnaticChannel, self).__init__(channel)
        if 'main_artist_match' in kwargs:
            self._main_artist_match = kwargs['main_artist_match']

    def song_metadata(self, filepath, album_title, is_chapter=False):
        # Extract the filename from the full path
        filename = os.path.basename(filepath)
        # Strip off the file extension
        filename_no_ext, _ = os.path.splitext(filename)

        song_title = None
        if is_chapter:
            # Strip off numeric prefix from title, which is there for chapters.
            song_title = re.sub(self._NUMERIC_PREFIX, "", filename_no_ext)
        else:
            song_title = album_title

        # Artist and Album Artist
        artist_match = re.match(self._main_artist_match, album_title)
        artist = None
        if artist_match:
            artist = artist_match.group(1)

        # Year
        year = re.findall(r"((?:19|20)\d\d)", album_title)

        # Extract track number from filename.
        track = None
        track_match = re.match(self._TRACK_PREFIX, filename_no_ext)
        if track_match:
            track = track_match.group(1)

        return SongMetadata(
            artist=artist,
            album_title=album_title,
            channel=self.name,
            song_title=song_title,
            track=track,
            year=year,
            genre=CarnaticChannel.GENRE
        )



CHANNELS = [
    CarnaticChannel("Carnatic Connect"),
    CarnaticChannel("Balu Karthikeyan"),
    CarnaticChannel(u"नादभृङ्ग Nādabhṛṅga"),
    CarnaticChannel("Shriram Vasudevan"),
    # The main artist is always at the beginning of the string before "-".
    # Example: "Madurai Mani Iyer | Wedding Concert, 1950’s"
    CarnaticChannel("Vaak", main_artist_match=r"^(.*?) \|")
]




