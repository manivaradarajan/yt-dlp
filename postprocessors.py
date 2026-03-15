"""yt-dlp PostProcessor classes for the download pipeline.

Clipping-related processors live in ``clipping.py``; ID3 tag writing is in
``metadata_processor.py``.
"""

import os
import re

from yt_dlp.postprocessor.common import PostProcessor

from channel import Channel  # noqa: F401 — imported for type documentation


class WriteDescriptionAsTxt(PostProcessor):
    """Writes the YouTube video description to a .txt file.

    For chapter-split albums the file lands *inside* the chapter directory
    (alongside the .m3u8 playlist).  For single-file videos it sits next to
    the audio file.

    yt-dlp's built-in writedescription always produces a .description file
    with no way to change the extension, so we handle it ourselves here.
    """

    def run(self, info):
        """Write description to the correct .txt path for this video.

        When ``FFmpegSplitChapters`` has run, chapter filepaths are already
        populated in ``info["chapters"]``, so we can detect the split case and
        redirect the .txt into the chapter directory instead of leaving it
        next to the album subdirectory.

        Args:
            info: yt-dlp info dictionary for the current file.

        Returns:
            A tuple of ([], info) as required by the PostProcessor interface.
        """
        filepath = info.get("filepath") or info.get("filename", "")
        description = info.get("description", "")
        if not filepath or not description:
            return [], info
        txt_path = self._txt_path(filepath, info.get("chapters"))
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(description)
        return [], info

    def _txt_path(self, filepath: str, chapters) -> str:
        """Return the path to write the .txt file to.

        For chapter-split videos, puts the file inside the chapter directory
        so it is grouped with the chapter MP3s and the .m3u8 playlist.
        For plain videos, puts it alongside the audio file.

        Args:
            filepath: Path of the main (unsplit) audio file.
            chapters: The ``info["chapters"]`` list, or None/empty.

        Returns:
            Absolute path for the .txt file.
        """
        split_chapters = [c for c in (chapters or []) if c.get("filepath")]
        if split_chapters:
            chapter_dir = os.path.dirname(split_chapters[0]["filepath"])
            name = os.path.splitext(os.path.basename(filepath))[0]
            return os.path.join(chapter_dir, name + ".txt")
        base, _ = os.path.splitext(filepath)
        return base + ".txt"


class WriteChapterPlaylist(PostProcessor):
    """Writes an M3U8 playlist for chapter-split audio files.

    Creates ``<chapter-dir>/<dir-name>.m3u8`` with one ``#EXTINF`` entry per
    chapter.  Only runs when the info dict contains chapters that have been
    assigned filepaths by ``FFmpegSplitChapters``.

    Videos without chapters are unaffected.
    Deletion of the unsplit original is handled by ``DeleteUnsplitAudio``.
    """

    def run(self, info):
        """Write the M3U8 playlist file when chapters were split.

        Args:
            info: yt-dlp info dictionary for the current file.

        Returns:
            A tuple of ([], info). File deletion is left to DeleteUnsplitAudio.
        """
        chapters = [c for c in (info.get("chapters") or []) if c.get("filepath")]
        if not chapters:
            return [], info

        chapter_dir = os.path.dirname(chapters[0]["filepath"])
        playlist_path = self._playlist_path(chapter_dir)
        lines = self._build_m3u8_lines(chapters)
        with open(playlist_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        return [], info

    def _playlist_path(self, chapter_dir: str) -> str:
        """Return the playlist filepath inside the chapter directory.

        Uses the directory name (already sanitized by yt-dlp) as the filename.

        Args:
            chapter_dir: Directory containing the chapter MP3 files.

        Returns:
            Absolute path to the ``.m3u8`` file.
        """
        name = os.path.basename(chapter_dir)
        return os.path.join(chapter_dir, f"{name}.m3u8")

    def _build_m3u8_lines(self, chapters: list) -> list[str]:
        """Build the M3U8 file lines for the given chapter list.

        Args:
            chapters: List of chapter dicts with ``filepath``, ``start_time``,
                and ``end_time`` keys.

        Returns:
            List of strings to join with newlines.
        """
        lines = ["#EXTM3U"]
        for chapter in chapters:
            filepath = chapter["filepath"]
            duration = int(chapter.get("end_time", 0) - chapter.get("start_time", 0))
            title = os.path.splitext(os.path.basename(filepath))[0]
            lines.append(f"#EXTINF:{duration},{title}")
            lines.append(os.path.basename(filepath))
        return lines


class DeleteUnsplitAudio(PostProcessor):
    """Removes the original unsplit MP3 after chapter splitting succeeds.

    When ``FFmpegSplitChapters`` runs it produces per-chapter files inside a
    subdirectory but leaves the original full-length file alongside them.
    This postprocessor instructs yt-dlp to delete that redundant file by
    returning it in the files-to-delete list.

    No-op when the video has no chapters or splitting was not performed.
    """

    def run(self, info):
        """Delete the unsplit file if chapter filepaths were produced.

        Args:
            info: yt-dlp info dictionary for the current file.

        Returns:
            A tuple of ([filepath_to_delete], info) when chapters were split,
            or ([], info) when splitting did not occur.
        """
        chapters = [c for c in (info.get("chapters") or []) if c.get("filepath")]
        if not chapters:
            return [], info
        return [info["filepath"]], info


class DeletePlaylistThumbnail(PostProcessor):
    """Deletes the channel-avatar JPG written for the playlist container entry.

    ``writethumbnail=True`` causes yt-dlp to download a thumbnail for the
    playlist container itself (the YouTube channel avatar).  Since there is no
    audio file to embed it into, ``EmbedThumbnailPP`` never runs on it and the
    file is never cleaned up.  This postprocessor removes it at the playlist
    phase, after yt-dlp has finished writing it to disk.

    The written path is stored in ``thumbnails[n]["filepath"]`` by the time the
    playlist phase fires.
    """

    def run(self, info):
        """Delete any thumbnail files written for this playlist entry.

        Args:
            info: yt-dlp info dictionary for the playlist container.

        Returns:
            A tuple of ([], info) as required by the PostProcessor interface.
        """
        for thumb in info.get("thumbnails") or []:
            filepath = thumb.get("filepath")
            if not filepath or not os.path.isfile(filepath):
                continue
            os.remove(filepath)
            # Remove the parent directory if it is now empty (yt-dlp doesn't).
            parent = os.path.dirname(filepath)
            try:
                os.rmdir(parent)
            except OSError:
                pass  # Not empty, or already gone.
        return [], info


class InjectArtistMetadata(PostProcessor):
    """Pre-process postprocessor that injects an ``artist`` field into the info dict.

    Runs *before* yt-dlp evaluates outtmpl, so the ``%(artist)s`` placeholder
    resolves to a meaningful directory name.  Falls back to the YouTube uploader
    name when no channel handler is registered or the title pattern does not match.
    """

    def __init__(
        self,
        channel_map: dict,
        artist_aliases: dict[str, str] | None = None,
        verbose: bool = False,
    ):
        """Initialise with a handle → Channel lookup dict and optional alias map.

        Args:
            channel_map: Maps YouTube handle strings (e.g. ``@CarnaticConnect``)
                to their :class:`Channel` instances.
            artist_aliases: Maps post-normalization artist names to their
                canonical form.  Applied after regex extraction and fallback.
            verbose: If True, print per-video artist resolution details.
        """
        super().__init__(None)
        self._channel_map = channel_map
        self._artist_aliases: dict[str, str] = artist_aliases or {}
        self._verbose = verbose

    def run(self, info):
        """Inject ``info["artist"]`` before outtmpl evaluation.

        Looks up the channel handler via ``_lookup_channel`` (tries
        ``uploader_id`` then ``channel_url``), calls ``_extract_artist`` on the
        video title, and falls back to the YouTube uploader name when no match
        is found so the field is never empty.  Applies ``artist_aliases`` after
        resolution.

        Args:
            info: yt-dlp info dictionary for the current video.

        Returns:
            A tuple of ([], info) as required by the PostProcessor interface.
        """
        title = info.get("title", "")
        channel, matched_handle = self._lookup_channel(info)
        artist = self._resolve_artist(info, channel, matched_handle, title)
        info["artist"] = self._apply_alias(artist, title)
        return [], info

    def _resolve_artist(
        self, info: dict, channel, matched_handle: str | None, title: str
    ) -> str:
        """Resolve the artist name from channel handler or uploader fallback.

        Args:
            info: yt-dlp info dictionary for the current video.
            channel: Matched :class:`Channel` instance, or ``None``.
            matched_handle: Handle string used to find ``channel``, or ``None``.
            title: Video title string.

        Returns:
            Resolved artist name (never empty).
        """
        if channel:
            artist = channel._extract_artist(title)
            if artist:
                if self._verbose:
                    print(f"[artist] '{title}' → '{artist}' (via {matched_handle})")
                return artist
            if self._verbose:
                print(
                    f"[artist] '{title}' — handle {matched_handle} found but"
                    f" no pattern matched; falling back to uploader"
                )
        elif self._verbose:
            uploader_id = info.get("uploader_id", "")
            channel_url = info.get("channel_url", "")
            print(
                f"[artist] '{title}' — no channel handler found"
                f" (uploader_id={uploader_id!r}, channel_url={channel_url!r});"
                f" falling back to uploader"
            )
        return info.get("uploader") or info.get("uploader_id") or "Unknown"

    def _apply_alias(self, artist: str, title: str) -> str:
        """Return the canonical name for ``artist`` from the alias map.

        When the artist has an alias and verbose mode is on, logs the mapping.

        Args:
            artist: Resolved artist name (post-normalization).
            title: Video title, used only for the verbose log.

        Returns:
            Aliased name if a mapping exists, otherwise ``artist`` unchanged.
        """
        aliased = self._artist_aliases.get(artist, artist)
        if aliased != artist and self._verbose:
            print(f"[artist] '{title}': alias '{artist}' → '{aliased}'")
        return aliased

    def _lookup_channel(self, info: dict) -> tuple:
        """Find the Channel handler for a video, trying multiple info fields.

        yt-dlp sometimes returns a UC-style channel ID in ``uploader_id`` rather
        than the ``@handle``, causing a lookup miss.  ``channel_url`` always
        contains the handle (``https://www.youtube.com/@Handle``), so it is used
        as a fallback.

        Args:
            info: yt-dlp info dictionary for the current video.

        Returns:
            Tuple of (Channel, handle_string) if found, or (None, None).
        """
        # Primary: uploader_id — normalise in case the @ is missing.
        uploader_id = info.get("uploader_id", "")
        handle = uploader_id if uploader_id.startswith("@") else f"@{uploader_id}"
        channel = self._channel_map.get(handle)
        if channel:
            return channel, handle

        # Fallback: extract the handle from channel_url (@Handle always present).
        channel_url = info.get("channel_url", "")
        m = re.search(r"/@([\w.]+)", channel_url)
        if m:
            handle = f"@{m.group(1)}"
            channel = self._channel_map.get(handle)
            if channel:
                return channel, f"{handle} (via channel_url)"
        return None, None
