"""Entry point for the Carnatic music downloader.

Configures yt-dlp with postprocessors for audio extraction, chapter splitting,
and thumbnail embedding.  Dispatches to named channel configs (``--channels``)
or single-video mode (``--url``) depending on CLI arguments.

Config discovery: every ``configs/*.py`` file that exports a module-level
``CONFIG: DownloadConfig`` is loaded automatically.  No changes to this file
are needed when adding a new config.
"""

import argparse
import copy
import datetime
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import yt_dlp
from yt_dlp.postprocessor.common import PostProcessor

from channel import Channel
from config import DownloadConfig
from metadata_processor import SetFileMetadata

# yt-dlp live_status values that indicate a broadcast/DVR stream.
# These streams use DASH/DVR format and don't support mid-stream seeking.
_BROADCAST_LIVE_STATUSES = ("is_live", "was_live", "post_live")

# Persists last-download dates per config name across runs.
_STATE_FILE = pathlib.Path.home() / ".yt-dlp-carnatic.json"

# Records downloaded video IDs; prevents re-downloads and enables early stopping.
_ARCHIVE_FILE = pathlib.Path.home() / ".yt-dlp-carnatic-archive.txt"


def _load_state() -> dict:
    """Load the persisted download state from disk.

    Returns:
        Dict mapping config name to ISO-format last-download date string,
        or an empty dict if the state file does not exist yet.
    """
    if not _STATE_FILE.exists():
        return {}
    with _STATE_FILE.open() as f:
        return json.load(f)


def _save_last_downloaded(config_names: list[str]) -> None:
    """Record today's date as the last-download date for each named config.

    Args:
        config_names: Config names (e.g. ``["carnatic"]``) to stamp with today.
    """
    state = _load_state()
    today = datetime.date.today().isoformat()
    for name in config_names:
        state[name] = today
    with _STATE_FILE.open("w") as f:
        json.dump(state, f, indent=2)


class _QuietLogger:
    """Custom yt-dlp logger: passes warnings and errors through; silences debug spam.

    When set as ``options["logger"]``, yt-dlp routes ``report_warning`` and
    ``report_error`` calls here instead of its own ``to_screen``, so they appear
    even when ``quiet=True`` is set globally.
    """

    def debug(self, msg: str) -> None:
        """Discard debug/info messages."""

    def warning(self, msg: str) -> None:
        """Print warnings to stderr.

        Args:
            msg: Warning message from yt-dlp.
        """
        print(f"WARNING: {msg}", file=sys.stderr)

    def error(self, msg: str) -> None:
        """Print errors to stderr.

        Args:
            msg: Error message from yt-dlp.
        """
        print(msg, file=sys.stderr)


def _make_progress_hook():
    """Return a progress hook that prints each file's basename once when it starts.

    Provides visible download progress in quiet mode, where yt-dlp's built-in
    progress bar is suppressed.

    Returns:
        A callable suitable for ``options["progress_hooks"]``.
    """
    seen: set[str] = set()

    def _hook(d: dict) -> None:
        if d["status"] != "downloading":
            return
        fn = d.get("filename", "")
        if fn and fn not in seen:
            seen.add(fn)
            print(f"[download] {os.path.basename(fn)}")

    return _hook


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


def _find_js_runtimes() -> dict:
    """Locate available JS runtimes and return a yt-dlp ``js_runtimes`` dict.

    Tries ``node`` then ``deno`` in order. Uses ``shutil.which`` so the result
    is correct regardless of how the venv's PATH differs from the login shell.

    Returns:
        Dict like ``{"node": {"path": "/opt/homebrew/bin/node"}}`` for the
        first runtime found, or ``{}`` if neither is on PATH.
    """
    for runtime in ("node", "deno"):
        path = shutil.which(runtime)
        if path:
            return {runtime: {"path": path}}
    return {}


# Default yt-dlp options used for all downloads.
# Derived from yt-dlp's cli_to_api.py tool.
# match_filter is NOT set here — it is applied dynamically in channel mode
# when the selected DownloadConfig has non-empty title_patterns.
OPTIONS = {
    "extract_flat": "discard_in_playlist",
    "final_ext": "mp3",
    "format": "bestaudio/best",
    "fragment_retries": 10,
    "concurrent_fragment_downloads": 8,
    "ignoreerrors": "only_download",
    "merge_output_format": "mp4",
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
    "js_runtimes": _find_js_runtimes(),
    # Download EJS challenge solver scripts from GitHub on first use.
    # Required for signature/n-parameter decryption alongside js_runtimes.
    "remote_components": {"ejs:github"},
    # Suppress chatty info messages; errors/warnings/progress are unaffected.
    # Pass --verbose to override.
    "quiet": True,
}


def load_configs() -> dict[str, DownloadConfig]:
    """Import all ``configs/*.py`` files and return a name → DownloadConfig dict.

    Each module must export ``CONFIG: DownloadConfig`` at module level.
    Files whose names start with ``_`` (e.g. ``__init__.py``) are skipped.

    Returns:
        Dict mapping ``DownloadConfig.name`` to the config instance.
    """
    configs: dict[str, DownloadConfig] = {}
    configs_dir = pathlib.Path(__file__).parent / "configs"
    for path in sorted(configs_dir.glob("*.py")):
        if path.name.startswith(("_", ".")):
            continue
        spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cfg: DownloadConfig = module.CONFIG
        configs[cfg.name] = cfg
    return configs


def resolve_configs(names_str: str) -> list[DownloadConfig]:
    """Parse a comma-separated config name string and return matching DownloadConfig objects.

    Args:
        names_str: Comma-separated config names, e.g. ``"carnatic,hindustani"``.

    Returns:
        List of matching DownloadConfig objects in the order they were requested.

    Raises:
        SystemExit: With a clear error message if any name is not found.
    """
    all_configs = load_configs()
    selected = []
    for name in names_str.split(","):
        name = name.strip()
        cfg = all_configs.get(name)
        if cfg is None:
            available = ", ".join(all_configs.keys())
            print(f"Unknown channel config '{name}'. Available: {available}")
            raise SystemExit(1)
        selected.append(cfg)
    return selected


def _format_config_entry(cfg: DownloadConfig, last_downloaded: str | None) -> str:
    """Format a DownloadConfig as a two-line display string for --list-channels.

    Args:
        cfg: The config to format.
        last_downloaded: ISO-format date of the last download, or None if never run.

    Returns:
        A string with the config name + description on the first line and the
        last-download date + channel handles indented on the second line.
    """
    last = f"last: {last_downloaded}" if last_downloaded else "never downloaded"
    identifiers = [ch.handle for ch in cfg.channels] + cfg.urls
    sources = "  ".join(identifiers)
    return f"{cfg.name:<20} {cfg.description}\n{'':20} {last}  {sources}"


def list_channels_and_exit() -> None:
    """Print all discovered channel configs and exit.

    Loads every ``configs/*.py`` file, prints name + description, last-download
    date, and channel handles for each, then exits with code 0.
    """
    configs = load_configs()
    state = _load_state()
    for cfg in configs.values():
        print(_format_config_entry(cfg, state.get(cfg.name)))
    raise SystemExit(0)


def make_title_filter(patterns: list[str], verbose: bool = False):
    """Return a yt-dlp ``match_filter`` callable for the given title patterns.

    A video passes the filter if its title matches *any* of the patterns.

    Args:
        patterns: List of regex patterns to match against video titles.
        verbose: If False, print rejection messages directly (they are suppressed
            by yt-dlp when ``quiet=True``). If True, yt-dlp shows them itself.

    Returns:
        A ``match_filter`` callable accepted by yt-dlp options.
    """

    def _filter(info_dict):
        title = info_dict.get("title", "")
        for pattern in patterns:
            if re.search(pattern, title):
                return None
        reason = f"'{title}' doesn't match any artist in the list"
        if not verbose:
            # quiet=True suppresses yt-dlp's own copy of this message, so we
            # print it ourselves to keep it visible as a progress indicator.
            print(f"[download] {reason}")
        return reason

    return _filter


def build_arg_parser() -> argparse.ArgumentParser:
    """Define and return the CLI argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o",
        "--output-directory",
        default=".",
        help="Output directory for downloaded files. Default: %(default)s",
    )
    parser.add_argument(
        "--no-split-chapters",
        action="store_false",
        dest="split_chapters",
        default=True,
        help="Disable splitting extracted audio into per-chapter files",
    )
    parser.add_argument(
        "--url",
        help="Download a single video instead of configured channels",
    )
    parser.add_argument(
        "--channels",
        metavar="NAME[,NAME2,...]",
        help="Comma-separated channel config names to download (see --list-channels)",
    )
    parser.add_argument(
        "--list-channels",
        action="store_true",
        default=False,
        help="List available channel configs and exit",
    )
    parser.add_argument("--start", help="Clip start time, e.g. 00:10:00")
    parser.add_argument("--end", help="Clip end time, e.g. 00:45:00")

    # --audio and --video are mutually exclusive; one is required with --url.
    media_group = parser.add_mutually_exclusive_group()
    media_group.add_argument(
        "--audio",
        action="store_true",
        default=False,
        help="Extract audio to MP3 (required with --url)",
    )
    media_group.add_argument(
        "--video",
        action="store_true",
        default=False,
        help="Download video instead of audio (required with --url)",
    )

    parser.add_argument(
        "--quality",
        metavar="HEIGHT",
        help="Maximum video height in pixels, e.g. 1080 or 720 (requires --video)",
    )
    parser.add_argument(
        "--prepend-date",
        action="store_true",
        default=False,
        help="Prepend the upload date (YYYYMMDD-) to output filenames",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Show full yt-dlp output (extraction steps, format selection, etc.)",
    )
    parser.add_argument(
        "--yt-dlp-opt",
        metavar="KEY=VALUE",
        action="append",
        dest="yt_dlp_opts",
        default=[],
        help=(
            "Extra yt-dlp option merged into the download options. "
            "VALUE is parsed as JSON so numbers and booleans work as expected "
            "(e.g. --yt-dlp-opt sleep_interval=2). Can be repeated."
        ),
    )
    return parser


def _parse_yt_dlp_opts(raw_opts: list[str]) -> dict:
    """Parse ``KEY=VALUE`` strings into a dict of yt-dlp options.

    VALUE is interpreted as JSON so that ``2`` becomes the int ``2`` and
    ``true`` becomes ``True``.  Bare strings that are not valid JSON are
    kept as-is.

    Args:
        raw_opts: List of ``"KEY=VALUE"`` strings from ``--yt-dlp-opt``.

    Returns:
        Dict mapping option keys to parsed values.
    """
    result = {}
    for kv in raw_opts:
        key, _, raw_value = kv.partition("=")
        try:
            result[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            result[key] = raw_value
    return result


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


def _setup_single_video(
    args: argparse.Namespace, options: dict
) -> tuple[CaptureFinalFilepath | None, list[Channel], list[str]]:
    """Validate and configure options for single-video ``--url`` mode.

    Args:
        args: Parsed CLI arguments (``args.url`` must be set).
        options: yt-dlp options dict to modify in-place.

    Returns:
        Tuple of (capturer, channels, urls).
        ``channels`` is empty — no ID3 tagging in single-video mode.
    """
    if not args.audio and not args.video:
        build_arg_parser().error("one of the arguments --audio --video is required")
    if args.quality and not args.video:
        build_arg_parser().error("--quality requires --video")

    capturer = None
    if args.start or args.end:
        capturer = configure_clip_options(
            options,
            args.url,
            args.start,
            args.end,
            is_video=bool(args.video or args.quality),
        )
    if args.video or args.quality:
        configure_video_mode(options, args.quality)

    # No channel handlers: single-video mode doesn't write ID3 tags.
    return capturer, [], [args.url]


def _setup_channel_mode(
    args: argparse.Namespace, options: dict
) -> tuple[list[Channel], list[str], list[str]]:
    """Load named configs and configure options for channel download mode.

    Args:
        args: Parsed CLI arguments (``args.channels`` must be set).
        options: yt-dlp options dict to modify in-place.

    Returns:
        Tuple of (channels, urls, config_names).
    """
    if not args.channels:
        build_arg_parser().error("--channels is required when not using --url")

    configs = resolve_configs(args.channels)

    all_channels = [ch for cfg in configs for ch in cfg.channels]
    all_patterns = [p for cfg in configs for p in cfg.title_patterns]

    # Use video mode if any selected config requests it.
    if any(cfg.output == "video" for cfg in configs):
        configure_video_mode(options)

    if all_patterns:
        options["match_filter"] = make_title_filter(all_patterns, verbose=args.verbose)

    # Record downloaded video IDs so re-runs skip already-downloaded content.
    options["download_archive"] = str(_ARCHIVE_FILE)

    all_urls = [url for ch in all_channels for url in ch.urls]
    all_urls += [url for cfg in configs for url in cfg.urls]
    return all_channels, all_urls, [cfg.name for cfg in configs]


def download_videos():
    """Parse CLI args, configure yt-dlp, and run the download."""
    args = build_arg_parser().parse_args()

    if args.list_channels:
        list_channels_and_exit()

    print(f"Output will be saved to: {args.output_directory}")
    options = build_options(
        args.output_directory, args.split_chapters, args.prepend_date
    )
    options.update(_parse_yt_dlp_opts(args.yt_dlp_opts))
    if args.verbose:
        options["quiet"] = False
        options["verbose"] = True
    else:
        # Route yt-dlp warnings/errors through our logger so they appear
        # despite quiet=True. Progress hook shows filenames as they download.
        options["logger"] = _QuietLogger()
        options["progress_hooks"] = [_make_progress_hook()]
    capturer = None

    config_names = []
    if args.url:
        capturer, channels, urls = _setup_single_video(args, options)
    else:
        channels, urls, config_names = _setup_channel_mode(args, options)
        print("Fetching channel playlist...")

    ydl = yt_dlp.YoutubeDL(options)
    ydl.add_post_processor(SetFileMetadata(channels=channels))
    ydl.add_post_processor(WriteDescriptionAsTxt())
    if capturer:
        # Register last so it sees the final filepath after all other postprocessors.
        ydl.add_post_processor(capturer)
    ydl.download(urls)

    if config_names:
        _save_last_downloaded(config_names)

    if capturer:
        run_post_clip(capturer, args.start, args.end)


if __name__ == "__main__":
    download_videos()
