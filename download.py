"""Entry point for the Carnatic music downloader.

Configures yt-dlp with postprocessors for audio extraction, chapter splitting,
and thumbnail embedding. Dispatches to channel downloads (from config.py) or
single-video mode depending on CLI arguments.
"""
import argparse
import copy
import os
import re
import subprocess

import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor

import config
from channel import CarnaticChannel
from metadata_processor import SetFileMetadata

# yt-dlp output filename templates.
CHANNEL_OUTTMPL = "%(channel)s/%(title)s.%(ext)s"
CHANNEL_VIDEO_OUTTMPL = "%(channel)s/%(title)s/%(title)s.%(ext)s"
CHANNEL_VIDEO_CHAPTER_OUTTMPL = (
    "%(channel)s/%(title)s/%(section_number)s %(section_title)s.%(ext)s"
)

# yt-dlp live_status values that indicate a broadcast/DVR stream.
# These streams use DASH/DVR format and don't support mid-stream seeking.
_BROADCAST_LIVE_STATUSES = ("is_live", "was_live", "post_live")


def title_filter(info_dict):
    """yt-dlp match_filter callback that filters videos by artist name.

    Args:
        info_dict: yt-dlp video info dictionary.

    Returns:
        None to allow the download, or an error string to skip it.
    """
    title = info_dict.get("title", "")
    for pattern in config.TITLE_PATTERNS:
        if re.search(pattern, title):
            return None
    return "'%s' doesn't match any artist in the list" % title


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


class WriteDescriptionAsTxt(PostProcessor):
    """Writes the YouTube video description to a .txt file alongside the downloaded file.

    yt-dlp's built-in writedescription always produces a .description file with no way
    to change the extension, so we handle it ourselves here.
    """

    def run(self, info):
        """Write description to <filepath_base>.txt.

        Args:
            info: yt-dlp info dictionary for the current file.

        Returns:
            A tuple of ([], info) as required by the PostProcessor interface.
        """
        filepath = info.get("filepath") or info.get("filename", "")
        description = info.get("description", "")
        if not filepath or not description:
            return [], info
        base, _ = os.path.splitext(filepath)
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(description)
        return [], info


# Default yt-dlp options used for all downloads.
# Derived from yt-dlp's cli_to_api.py tool.
OPTIONS = {
    "extract_flat": "discard_in_playlist",
    "final_ext": "mp3",
    "format": "bestaudio/best",
    "fragment_retries": 10,
    "concurrent_fragment_downloads": 8,
    "ignoreerrors": "only_download",
    "merge_output_format": "mp4",
    "outtmpl": {
        "default": CHANNEL_OUTTMPL,
        "chapter": CHANNEL_VIDEO_CHAPTER_OUTTMPL,
        "thumbnail": CHANNEL_VIDEO_OUTTMPL,
    },
    "postprocessors": [
        {"format": "jpg", "key": "FFmpegThumbnailsConvertor", "when": "before_dl"},
        {
            "key": "FFmpegExtractAudio",
            "nopostoverwrites": False,
            "preferredcodec": "mp3",
            "preferredquality": "5",
        },
        {
            "add_chapters": True,
            "add_infojson": "if_exists",
            "add_metadata": True,
            "key": "FFmpegMetadata",
        },
        {"already_have_thumbnail": True, "key": "EmbedThumbnail"},
        {"force_keyframes": False, "key": "FFmpegSplitChapters"},
        {"key": "FFmpegConcat", "only_multi_video": True, "when": "playlist"},
    ],
    "retries": 10,
    "writethumbnail": True,
    "embedthumbnail": True,
    "embedmetadata": True,
    "addmetadata": True,
    "yesplaylist": True,
    "js_runtimes": {"node": {}},
    "match_filter": title_filter,
}


def build_arg_parser() -> argparse.ArgumentParser:
    """Define and return the CLI argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o", "--output-directory",
        default=".",
        help="Output directory for downloaded files. Default: %(default)s",
    )
    parser.add_argument(
        "--split-chapters",
        action="store_false",
        default=True,
        help="Split extracted audio into per-chapter files. Default: %(default)s",
    )
    parser.add_argument("--url", help="Download a single video instead of configured channels")
    parser.add_argument("--start", help="Clip start time, e.g. 00:10:00")
    parser.add_argument("--end", help="Clip end time, e.g. 00:45:00")
    parser.add_argument(
        "--video",
        action="store_true",
        default=False,
        help="Download video instead of extracting audio to MP3",
    )
    parser.add_argument(
        "--quality",
        metavar="HEIGHT",
        help="Maximum video height in pixels, e.g. 1080 or 720 (implies --video)",
    )
    parser.add_argument(
        "--prepend-date",
        action="store_true",
        default=False,
        help="Prepend the upload date (YYYYMMDD-) to output filenames",
    )
    return parser


def title_prefix(prepend_date: bool) -> str:
    """Return the filename prefix to use for video titles.

    Args:
        prepend_date: If True, prefix filenames with the upload date.

    Returns:
        A yt-dlp template string to prepend to %(title)s.
    """
    # release_date is when the video went public (correct for live streams/premieres).
    # Falls back to upload_date for regular videos where release_date isn't set.
    return "%(release_date|upload_date)s-" if prepend_date else ""


def build_options(output_dir: str, split_chapters: bool, prepend_date: bool) -> dict:
    """Return a deep copy of OPTIONS with output paths and split_chapters applied.

    Args:
        output_dir: Root directory for all output files.
        split_chapters: Whether to split audio into per-chapter files.
        prepend_date: Whether to prepend the upload date to output filenames.

    Returns:
        A fully configured yt-dlp options dict.
    """
    options = copy.deepcopy(OPTIONS)
    options["split_chapters"] = split_chapters
    prefix = title_prefix(prepend_date)
    options["outtmpl"] = {
        "default": f"{output_dir}/%(channel)s/{prefix}%(title)s.%(ext)s",
        "chapter": f"{output_dir}/%(channel)s/{prefix}%(title)s/%(section_number)s %(section_title)s.%(ext)s",
        "thumbnail": f"{output_dir}/%(channel)s/{prefix}%(title)s/{prefix}%(title)s.%(ext)s",
    }
    return options


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


def remove_postprocessor(options: dict, key: str) -> None:
    """Remove a postprocessor by key from the options dict in-place.

    Args:
        options: yt-dlp options dict.
        key: The postprocessor key to remove (e.g. "FFmpegExtractAudio").
    """
    options["postprocessors"] = [
        pp for pp in options["postprocessors"] if pp["key"] != key
    ]


def video_format(max_height: str | None) -> str:
    """Return a yt-dlp format selector for video, optionally capped at a resolution.

    Prefers separate DASH video+audio streams for maximum quality,
    falling back to a combined HLS stream if DASH is unavailable.

    Args:
        max_height: Maximum video height in pixels (e.g. "1080"), or None for best available.

    Returns:
        A yt-dlp format selector string.
    """
    if max_height:
        return f"bestvideo[height<={max_height}]+bestaudio/best[height<={max_height}]"
    return "bestvideo+bestaudio/best"


def configure_video_mode(options: dict, max_height: str | None = None) -> None:
    """Switch options from audio extraction to full video download in-place.

    Args:
        options: yt-dlp options dict to modify.
        max_height: Maximum video height in pixels (e.g. "1080"), or None for best available.
    """
    options["format"] = video_format(max_height)
    del options["final_ext"]
    remove_postprocessor(options, "FFmpegExtractAudio")


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


def run_post_clip(capturer: CaptureFinalFilepath, start: str | None, end: str | None) -> None:
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


def make_channels() -> list:
    """Return the list of registered channel handlers for metadata tagging.

    Returns:
        List of Channel instances, one per supported YouTube channel.
    """
    return [
        CarnaticChannel("Carnatic Connect"),
        CarnaticChannel("Balu Karthikeyan"),
        CarnaticChannel("नादभृङ्ग Nādabhṛṅga"),
        CarnaticChannel("Shriram Vasudevan"),
        # Vaak titles use "Artist | Concert title" rather than "Artist - Concert title".
        CarnaticChannel("Vaak", main_artist_match=r"^(.*?) \|"),
    ]


def download_videos():
    """Parse CLI args, configure yt-dlp, and run the download."""
    args = build_arg_parser().parse_args()
    print(f"Output will be saved to: {args.output_directory}")

    options = build_options(args.output_directory, args.split_chapters, args.prepend_date)
    capturer = None

    if args.url:
        # Single-video mode: bypass the channel title filter.
        del options["match_filter"]
        if args.start or args.end:
            capturer = configure_clip_options(
                options, args.url, args.start, args.end, is_video=bool(args.video or args.quality)
            )
        if args.video or args.quality:
            configure_video_mode(options, args.quality)
        urls = [args.url]
    else:
        urls = config.URLS

    ydl = yt_dlp.YoutubeDL(options)
    ydl.add_post_processor(SetFileMetadata(channels=make_channels()))
    ydl.add_post_processor(WriteDescriptionAsTxt())
    if capturer:
        # Register last so it sees the final filepath after all other postprocessors.
        ydl.add_post_processor(capturer)
    ydl.download(urls)

    if capturer:
        run_post_clip(capturer, args.start, args.end)


# TODO: Remove once final
if __name__ == "__main__":
    download_videos()
