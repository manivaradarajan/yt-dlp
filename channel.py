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
    def __init__(self, channel):
        self.channel = channel

    @abstractmethod
    def song_metadata(self, filepath, album_title, is_chapter=False):
        pass


class CarnaticConnect(Channel):
    NUMERIC_PREFIX = r"^[\s0-9\. ]+"
    TRACK_PREFIX = r"^(\d+) "
    MAIN_ARTIST_MATCH = r"^(.*?) -"

    CHANNEL = "Carnatic Connect"
    GENRE = "Carnatic"

    def __init__(self):
        super(CarnaticConnect, self).__init__(CarnaticConnect.CHANNEL)

    def song_metadata(self, filepath, album_title, is_chapter=False):
        # Extract the filename from the full path
        filename = os.path.basename(filepath)
        # Strip off the file extension
        filename_no_ext, _ = os.path.splitext(filename)

        song_title = None
        if is_chapter:
            # Strip off numeric prefix from title, which is there for chapters.
            song_title = re.sub(self.NUMERIC_PREFIX, "", filename_no_ext)
        else:
            song_title = album_title

        # Artist and Album Artist
        artist_match = re.match(self.MAIN_ARTIST_MATCH, album_title)
        artist = None
        if artist_match:
            artist = artist_match.group(1)

        # Year
        year = re.findall(r"((?:19|20)\d\d)", album_title)

        # Extract track number from filename.
        track = None
        track_match = re.match(self.TRACK_PREFIX, filename_no_ext)
        if track_match:
            track = track_match.group(1)

        return SongMetadata(
            artist=artist,
            album_title=album_title,
            channel=CarnaticConnect.CHANNEL,
            song_title=song_title,
            track=track,
            year=year,
            genre=CarnaticConnect.GENRE
        )

