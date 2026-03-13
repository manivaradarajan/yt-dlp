"""Postprocessor that writes ID3 tags to downloaded MP3 files.

After yt-dlp extracts audio, SetFileMetadata looks up the registered Channel
handler by channel name and uses it to derive and write ID3 tags via mutagen.
"""
import os

from mutagen import id3, mp3
from yt_dlp.postprocessor.common import PostProcessor

from channel import Channel, SongMetadata


class SetFileMetadata(PostProcessor):
    """yt-dlp PostProcessor that writes ID3 tags to downloaded MP3 files."""

    def __init__(self, downloader=None, channels=None, **kwargs):
        """Initialise with a list of Channel handlers.

        Args:
            downloader: yt-dlp downloader instance (passed by yt-dlp internals).
            channels: List of Channel instances to register for metadata lookup.
        """
        super().__init__(downloader, **kwargs)
        self._channels: dict[str, Channel] = {}
        if not channels:
            print("No channels specified. May not set id3 tags correctly.")
            return
        for channel in channels:
            self._channels[channel.name] = channel

    def _set_song_metadata(self, filepath: str, song_metadata: SongMetadata) -> None:
        """Write ID3 tags to an MP3 file.

        Args:
            filepath: Path to the MP3 file.
            song_metadata: Metadata to write.
        """
        audio_file = mp3.MP3(filepath, ID3=id3.ID3)
        try:
            audio_file.add_tags()
        except Exception:
            pass  # Tags already exist.

        audio_file.tags["TIT2"] = id3.TIT2(encoding=3, text=song_metadata.song_title)
        audio_file.tags["TALB"] = id3.TALB(encoding=3, text=song_metadata.album_title)

        if song_metadata.artist:
            audio_file.tags["TPE1"] = id3.TPE1(encoding=3, text=song_metadata.artist)
            audio_file.tags["TPE2"] = id3.TPE2(encoding=3, text=song_metadata.artist)

        if song_metadata.year:
            audio_file.tags["TDRC"] = id3.TDRC(encoding=3, text=song_metadata.year)
        else:
            audio_file.tags.pop("TDRC", None)

        if song_metadata.track:
            audio_file.tags["TRCK"] = id3.TRCK(encoding=3, text=song_metadata.track)
        else:
            audio_file.tags.pop("TRCK", None)

        if song_metadata.genre:
            audio_file.tags["TCON"] = id3.TCON(encoding=3, text=song_metadata.genre)

        audio_file.save()

    def run(self, info):
        """Write ID3 tags for the main file and any chapter splits.

        Only runs for MP3 files; silently skips video or other formats.

        Args:
            info: yt-dlp info dictionary for the current file.

        Returns:
            A tuple of ([], info) as required by the PostProcessor interface.
        """
        if info["ext"] != "mp3":
            return [], info

        channel_name = info.get("channel", "")
        handler = self._channels.get(channel_name)
        if not handler:
            print(f"Warning: Channel '{channel_name}' not registered, skipping ID3 tags.")
            return [], info

        md = handler.song_metadata(info["filepath"], info["title"])
        self._set_song_metadata(info["filepath"], md)

        for chapter in info.get("chapters", []):
            chapter_md = handler.song_metadata(chapter["filepath"], info["title"], is_chapter=True)
            self._set_song_metadata(chapter["filepath"], chapter_md)

        return [], info
