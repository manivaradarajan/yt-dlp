import abc
import os
from abc import abstractmethod

import mutagen
from mutagen import id3
from mutagen import mp3

import re


class ChannelMetadata(abc.ABC):
    def __init__(self, channel):
        self.channel = channel

    @abstractmethod
    def set_metadata(self, filepath, album_title, is_chapter=False):
        pass


class CarnaticConnectMetadata(ChannelMetadata):
    NUMERIC_PREFIX = r'^[\s0-9\. ]+'
    TRACK_PREFIX = r'^(\d+) '
    MAIN_ARTIST_MATCH = r'^(.*?) -'

    def __init__(self):
        super(CarnaticConnectMetadata, self).__init__("Carnatic Connect")

    def set_metadata(self, filepath, album_title, is_chapter=False):
        audio_file = mp3.MP3(filepath, ID3=id3.ID3)
        try:
            audio_file.add_tags()
        except Exception:
            # Already has tags.
            pass

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

        # Title
        audio_file.tags["TIT2"] = id3.TIT2(encoding=3, text=song_title)

        # Artist and Album Artist
        artist_match = re.match(self.MAIN_ARTIST_MATCH, album_title)
        if artist_match:
            artist = artist_match.group(1)
            audio_file.tags["TPE1"] = id3.TPE1(encoding=3, text=artist)
            audio_file.tags["TPE2"] = id3.TPE2(encoding=3, text=artist)

        # Album
        audio_file.tags["TALB"] = id3.TALB(encoding=3, text=album_title)

        # Year
        year = re.findall(r'((?:19|20)\d\d)', album_title)
        if year:
            audio_file.tags['TDRC'] = id3.TDRC(encoding=3, text=year)
        else:
            del audio_file.tags['TDRC']

        # Extract track number from filename.
        track_match = re.match(self.TRACK_PREFIX, filename_no_ext)
        if track_match:
            track = track_match.group(1)
            audio_file.tags["TRCK"] = id3.TRCK(encoding=3, text=track)
        else:
            del audio_file.tags['TRCK']

        audio_file.save()
