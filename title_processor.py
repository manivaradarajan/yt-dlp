import os
import re

import mutagen
import yt_dlp
from mutagen import id3, mp3
from yt_dlp.postprocessor.common import PostProcessor

import channel
from channel import Channel, SongMetadata


class SetFileMetadata(PostProcessor):
    # Dict of "name" -> Channel.
    _channels = {}

    def __init__(self, downloader=None, channels=None, **kwargs):
        super(SetFileMetadata, self).__init__(downloader, **kwargs)
        if not channels:
            print("No channels specified. May not set id3 tags correctly.")
            return
        [self._add_channel(c) for c in channels]

    def _add_channel(self, channel: Channel):
        self._channels[channel.name] = channel

    def _set_song_metadata(self, filepath, song_metadata):
        audio_file = mp3.MP3(filepath, ID3=id3.ID3)
        try:
            audio_file.add_tags()
        except Exception:
            # Already has tags.
            pass

        # Title
        audio_file.tags["TIT2"] = id3.TIT2(encoding=3, text=song_metadata.song_title)

        # Artist and Album Artist
        if song_metadata.artist:
            audio_file.tags["TPE1"] = id3.TPE1(encoding=3, text=song_metadata.artist)
            audio_file.tags["TPE2"] = id3.TPE2(encoding=3, text=song_metadata.artist)

        # Album
        audio_file.tags["TALB"] = id3.TALB(encoding=3, text=song_metadata.album_title)

        # Year
        if song_metadata.year:
            audio_file.tags["TDRC"] = id3.TDRC(encoding=3, text=song_metadata.year)
        else:
            del audio_file.tags["TDRC"]

        # Extract track number from filename.
        if song_metadata.track:
            audio_file.tags["TRCK"] = id3.TRCK(encoding=3, text=song_metadata.track)
        else:
            del audio_file.tags["TRCK"]

        if song_metadata.genre:
            audio_file.tags["TCON"] = id3.TCON(encoding=3, text=song_metadata.genre)

        audio_file.save()

    def run(self, info):
        if info["ext"] == "mp3":
            try:
                channel = self._channels[info["channel"]]

                # Set the ID3 tags for the main un-split audio file.
                md = channel.song_metadata(info["filepath"], info["title"])
                self._set_song_metadata(info["filepath"], md)

                # Iterate through the chapters and set the ID3 tags for each.
                for i, chapter in enumerate(info["chapters"]):
                    chapter_md = channel.song_metadata(
                        chapter["filepath"], info["title"], is_chapter=True
                    )
                    self._set_song_metadata(chapter["filepath"], chapter_md)
            except KeyError:
                print("Warning: Channel '%s' not registered" % info["channel"])
                pass

        return [], info
