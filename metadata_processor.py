"""Postprocessor that writes ID3 tags to downloaded MP3 files.

After yt-dlp extracts audio, ``SetFileMetadata`` looks up the registered
``Channel`` handler by its YouTube handle and uses it to derive and write ID3
tags via mutagen.
"""

import os

from mutagen import id3, mp3
from yt_dlp.postprocessor.common import PostProcessor

from channel import Channel, SongMetadata


def _normalize_handle(uploader_id: str) -> str:
    """Ensure a yt-dlp ``uploader_id`` value carries the ``@`` prefix.

    yt-dlp may omit the ``@`` from ``uploader_id`` for some channels, so we
    normalise it before looking up the handler dict.

    Args:
        uploader_id: The raw ``uploader_id`` string from the yt-dlp info dict.

    Returns:
        The handle with a leading ``@``, e.g. ``@CarnaticConnect``.
    """
    if uploader_id and not uploader_id.startswith("@"):
        return f"@{uploader_id}"
    return uploader_id


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
        for channel in (channels or []):
            # Key by handle so we can look up via yt-dlp's uploader_id field.
            self._channels[channel.handle] = channel

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

        # uploader_id is the channel handle (e.g. "CarnaticConnect" or "@CarnaticConnect").
        uploader_id = info.get("uploader_id", "")
        handle = _normalize_handle(uploader_id)
        handler = self._channels.get(handle)
        if not handler:
            # Only warn when channels were registered but this handle isn't among them
            # (genuine misconfiguration). Silence when no channels were registered at
            # all — expected for urls-only configs and single-video mode.
            if self._channels:
                print(
                    f"Warning: Channel handle '{handle}' not registered, skipping ID3 tags."
                )
            return [], info

        md = handler.song_metadata(info["filepath"], info["title"])
        self._set_song_metadata(info["filepath"], md)

        for chapter in info.get("chapters", []):
            chapter_md = handler.song_metadata(
                chapter["filepath"], info["title"], is_chapter=True
            )
            self._set_song_metadata(chapter["filepath"], chapter_md)

        return [], info
