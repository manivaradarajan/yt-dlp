"""Broadcast detection and time-range clipping for single-video downloads.

Two strategies: direct clip via ``download_ranges`` (regular videos) and ffmpeg
second-pass (live/DVR streams).  ``CaptureFinalFilepath`` is a PostProcessor
helper used only by the broadcast fallback path.
"""

import os
import subprocess

import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor

# yt-dlp live_status values that indicate a broadcast/DVR stream.
# These streams use DASH/DVR format and don't support mid-stream seeking.
_BROADCAST_LIVE_STATUSES = ("is_live", "was_live", "post_live")


def remove_postprocessor(options: dict, key: str) -> None:
    """Remove a postprocessor by key from the options dict in-place.

    Args:
        options: yt-dlp options dict.
        key: The postprocessor key to remove (e.g. ``"FFmpegExtractAudio"``).
    """
    options["postprocessors"] = [
        pp for pp in options["postprocessors"] if pp["key"] != key
    ]


def parse_time(t: str) -> float:
    """Convert a time string to seconds.

    Args:
        t: Time string in HH:MM:SS, MM:SS, or raw seconds format.

    Returns:
        The time in seconds as a float.
    """
    parts = t.split(":")
    return sum(float(p) * 60**i for i, p in enumerate(reversed(parts)))


def clip_file(filepath: str, start: str | None, end: str | None) -> None:
    """Clip a media file to the given time range using ffmpeg, replacing the original in-place.

    Args:
        filepath: Path to the media file to clip.
        start: Clip start time (HH:MM:SS), or None to start from the beginning.
        end: Clip end time (HH:MM:SS), or None to clip to the end.
    """
    base, ext = os.path.splitext(filepath)
    tmp_path = f"{base}_clip{ext}"
    # Both -ss and -to must be input options (before -i) so they are treated as
    # absolute timestamps in the source file. If -to is placed after -i it becomes
    # an output option and is interpreted as a duration from the start of output.
    cmd = ["ffmpeg", "-y"]
    if start:
        cmd += ["-ss", start]
    if end:
        cmd += ["-to", end]
    cmd += ["-i", filepath, "-c", "copy", tmp_path]  # stream-copy: no re-encode
    subprocess.run(cmd, check=True)
    os.replace(tmp_path, filepath)


class CaptureFinalFilepath(PostProcessor):
    """yt-dlp PostProcessor that records the output filepath after all processing.

    Used in the broadcast fallback path so we know which file to clip with ffmpeg.
    """

    def __init__(self):
        super().__init__(None)
        self.filepaths: list[str] = []

    def run(self, info):
        """Append the current filepath to self.filepaths and pass info through unchanged.

        Args:
            info: yt-dlp info dictionary for the current file.

        Returns:
            A tuple of ([], info) as required by the PostProcessor interface.
        """
        fp = info.get("filepath") or info.get("filename")
        if fp:
            self.filepaths.append(fp)
        return [], info


def probe_video(url: str) -> dict:
    """Fetch video metadata from YouTube without downloading.

    Args:
        url: YouTube video URL.

    Returns:
        yt-dlp info dictionary for the video.
    """
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
        return ydl.extract_info(url, download=False)


def video_is_broadcast(info: dict) -> bool:
    """Return True if the video is a live or DVR broadcast stream.

    Args:
        info: yt-dlp info dictionary for the video.

    Returns:
        True if the video is a broadcast/DVR stream.
    """
    live_status = info.get("live_status", "")
    return (
        live_status in _BROADCAST_LIVE_STATUSES
        or bool(info.get("is_live"))
        or bool(info.get("was_live"))
    )


def configure_direct_clip(options: dict, start: str | None, end: str | None) -> None:
    """Configure yt-dlp to download only the specified time range during download.

    Args:
        options: yt-dlp options dict to modify.
        start: Clip start time (HH:MM:SS), or None for the beginning.
        end: Clip end time (HH:MM:SS), or None for the end.
    """
    start_sec = parse_time(start) if start else 0.0
    end_sec = parse_time(end) if end else float("inf")
    options["download_ranges"] = lambda info, ydl: [
        {"start_time": start_sec, "end_time": end_sec}
    ]
    options["force_keyframes_at_cuts"] = True
    print(f"  Downloading clip {start or 'start'} → {end or 'end'}...")


def configure_broadcast_fallback(
    options: dict, title: str, is_video: bool
) -> CaptureFinalFilepath:
    """Configure options to download the full broadcast; clipping happens afterward via ffmpeg.

    Args:
        options: yt-dlp options dict to modify.
        title: Video title, used for user-facing messages.
        is_video: True if downloading video, False for audio.

    Returns:
        A CaptureFinalFilepath instance to register as a postprocessor,
        so the output filepath is available for ffmpeg clipping.
    """
    media_type = "video" if is_video else "audio"
    print(f"  '{title}' is a live/DVR broadcast.")
    print(
        f"  YouTube's DASH/DVR format doesn't support mid-stream seeking,"
        f" so the full {media_type} must be downloaded first."
    )
    print(f"  Step 1/2: Downloading full {media_type}...")
    # Chapter splitting doesn't make sense for a range we'll clip afterward.
    remove_postprocessor(options, "FFmpegSplitChapters")
    return CaptureFinalFilepath()


def configure_clip_options(
    options: dict, url: str, start: str | None, end: str | None, is_video: bool
) -> CaptureFinalFilepath | None:
    """Probe the URL and configure clipping based on whether it's a broadcast or regular video.

    Args:
        options: yt-dlp options dict to modify.
        url: YouTube video URL to probe.
        start: Clip start time (HH:MM:SS), or None.
        end: Clip end time (HH:MM:SS), or None.
        is_video: True if downloading video, False for audio.

    Returns:
        A CaptureFinalFilepath instance for broadcast streams (clipped post-download),
        or None for regular videos (clipped during download via download_ranges).
    """
    print("Checking video info...")
    info = probe_video(url)
    if video_is_broadcast(info):
        return configure_broadcast_fallback(options, info.get("title", url), is_video)
    configure_direct_clip(options, start, end)
    return None


def run_post_clip(
    capturer: CaptureFinalFilepath, start: str | None, end: str | None
) -> None:
    """Clip all files captured during download to the given time range using ffmpeg.

    Args:
        capturer: PostProcessor instance that recorded downloaded filepaths.
        start: Clip start time (HH:MM:SS), or None for the beginning.
        end: Clip end time (HH:MM:SS), or None for the end.
    """
    clip_range = f"{start or 'start'} → {end or 'end'}"
    print(f"\nStep 2/2: Clipping {clip_range} using ffmpeg...")
    for fp in capturer.filepaths:
        print(f"  Clipping '{fp}'...")
        clip_file(fp, start, end)
        print(f"  Done.")
