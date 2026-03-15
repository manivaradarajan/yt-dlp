"""Entry point for the Carnatic music downloader.

Configures yt-dlp with postprocessors for audio extraction, chapter splitting,
and thumbnail embedding.  Dispatches to named channel configs (``--channels``)
or single-video mode (``--url``) depending on CLI arguments.

Config discovery: every ``configs/*.py`` file that exports a module-level
``CONFIG: DownloadConfig`` is loaded automatically.  No changes to this file
are needed when adding a new config.

PostProcessor classes live in ``postprocessors.py``.
Broadcast detection and clipping helpers are in ``clipping.py``.
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
import sys

import yt_dlp

from channel import Channel
from clipping import (
    CaptureFinalFilepath,
    configure_clip_options,
    remove_postprocessor,
    run_post_clip,
)
from config import DownloadConfig
from metadata_processor import SetFileMetadata
from postprocessors import (
    DeletePlaylistThumbnail,
    DeleteUnsplitAudio,
    InjectArtistMetadata,
    WriteChapterPlaylist,
    WriteDescriptionAsTxt,
)

# Persists last-download dates per config name across runs.
_STATE_FILE = pathlib.Path.home() / ".yt-dlp-state.json"

# Records downloaded video IDs; prevents re-downloads and enables early stopping.
_ARCHIVE_FILE = pathlib.Path.home() / ".yt-dlp-archive.txt"


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


_CYAN = "\033[36m"
_GREEN = "\033[32m"
_GREY = "\033[90m"
_RESET = "\033[0m"
_BAR_WIDTH = 20
_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip_ansi(s: str) -> str:
    """Return *s* with all ANSI escape codes removed."""
    return _ANSI_RE.sub("", s)

# Human-readable labels for postprocessors that take noticeable time.
# Keys are the values returned by each class's pp_key() method.
_PP_LABELS: dict[str, str] = {
    "ExtractAudio": "Extracting audio",
    "SplitChapters": "Splitting chapters",
    "EmbedThumbnail": "Embedding thumbnail",
}


def _format_speed(bps: float) -> str:
    """Format a byte-per-second rate as a human-readable string.

    Args:
        bps: Speed in bytes per second.

    Returns:
        String like ``"2.3 MB/s"`` or ``"512 KB/s"``.
    """
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.1f} MB/s"
    return f"{bps / 1_000:.0f} KB/s"


def _format_eta(seconds: int) -> str:
    """Format an ETA in seconds as a human-readable string.

    Args:
        seconds: Estimated seconds remaining.

    Returns:
        String like ``"1:23"`` (minutes:seconds) or ``"45s"``.
    """
    if seconds >= 60:
        return f"{seconds // 60}:{seconds % 60:02d}"
    return f"{seconds}s"


def _format_size(n: int) -> str:
    """Format a byte count as a compact human-readable string.

    Args:
        n: Number of bytes.

    Returns:
        String like ``"34.2 MB"`` or ``"512 KB"``.
    """
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    return f"{n / 1_000:.0f} KB"


def _make_bar(pct: int, width: int = _BAR_WIDTH) -> str:
    """Build a coloured block-character progress bar.

    Args:
        pct: Integer percentage 0–100.
        width: Total number of block characters.

    Returns:
        ANSI-coloured string ``"████░░░░░░░░"`` of *width* characters.
    """
    filled = round(width * pct / 100)
    bar = _CYAN + "█" * filled + _GREY + "░" * (width - filled) + _RESET
    return bar


def _build_progress_suffix(d: dict) -> str:
    """Build the right-hand portion of a progress line (bar, %, speed, ETA).

    Args:
        d: yt-dlp progress dict for the current tick.

    Returns:
        ANSI-coloured string with bar + stats, without the filename prefix.
    """
    downloaded = d.get("downloaded_bytes") or 0
    total = d.get("total_bytes") or 0  # estimates are too unreliable
    speed = d.get("speed")
    eta = d.get("eta")

    parts: list[str] = []
    if total:
        pct = min(100, downloaded * 100 // total)
        parts.append(_make_bar(pct))
        parts.append(f"{_CYAN}{pct:3d}%{_RESET}")
        parts.append(_format_size(downloaded) + "/" + _format_size(total))
    else:
        parts.append(_format_size(downloaded))

    if speed:
        parts.append(f"{_GREEN}{_format_speed(speed)}{_RESET}")
    if eta is not None:
        parts.append(f"ETA {_format_eta(eta)}")

    return "  ".join(parts)


def _build_progress_line(name: str, d: dict) -> str:
    """Compose the single-line progress string, truncated to terminal width.

    Truncates the filename with ``…`` so the whole line never exceeds the
    terminal width — preventing line wrap that breaks ``\\r`` overwriting.

    Args:
        name: Basename of the file being downloaded.
        d: yt-dlp progress dict for the current tick.

    Returns:
        Plain-plus-ANSI string ready for ``print(..., end="")``.
    """
    prefix = "[download] "
    suffix = _build_progress_suffix(d)
    sep = "  "

    term_cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    # Visible chars used by prefix + sep + suffix; remainder is for the name.
    max_name = term_cols - len(prefix) - len(sep) - len(_strip_ansi(suffix))
    max_name = max(10, max_name)
    if len(name) > max_name:
        name = name[: max_name - 1] + "…"

    return f"{prefix}{name}{sep}{suffix}"


def _make_progress_hook():
    """Return a live single-line progress hook for quiet-mode downloads.

    Uses ``\\r`` to overwrite the current terminal line on each tick.
    When a new file starts the previous line is finalised with ``\\n``.

    Returns:
        A callable suitable for ``options["progress_hooks"]``.
    """
    active_fn: list[str] = [""]  # list used as mutable cell for nonlocal
    last_len: list[int] = [0]

    def _print_line(line: str) -> None:
        """Overwrite the current terminal line with *line*."""
        vis = len(_strip_ansi(line))
        padding = max(0, last_len[0] - vis)
        print(f"\r{line}{' ' * padding}", end="", flush=True)
        last_len[0] = vis

    def _finish_line() -> None:
        """Move to the next line after a file completes or changes."""
        if last_len[0]:
            print()
            last_len[0] = 0

    def _hook(d: dict) -> None:
        fn = d.get("filename", "")
        if not fn:
            return

        if d["status"] == "finished":
            _finish_line()
            active_fn[0] = ""
            return

        if d["status"] != "downloading":
            return

        name = os.path.basename(fn)

        if fn != active_fn[0]:
            _finish_line()
            active_fn[0] = fn

        _print_line(_build_progress_line(name, d))

    return _hook


def _make_postprocessor_hook():
    """Return a postprocessor hook that logs the start of slow ffmpeg stages.

    Fires for each postprocessor that has a label in ``_PP_LABELS``.  Runs
    only in quiet mode (not wired up when ``--verbose`` is active).

    Returns:
        A callable suitable for ``ydl.add_postprocessor_hook()``.
    """

    def _hook(d: dict) -> None:
        if d.get("status") != "started":
            return
        label = _PP_LABELS.get(d.get("postprocessor", ""))
        if label:
            print(f"[postprocess] {label}...")

    return _hook


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
        {"already_have_thumbnail": False, "key": "EmbedThumbnail"},
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


def make_title_filter(
    patterns: list[str],
    exclude_patterns: list[str] | None = None,
    verbose: bool = False,
):
    """Return a yt-dlp ``match_filter`` callable for the given title patterns.

    A video passes the filter if:
    - Its title matches *at least one* of ``patterns`` (when non-empty), AND
    - Its title does NOT match any of ``exclude_patterns`` (when non-empty).

    Args:
        patterns: Allowlist of regex patterns. Empty list skips allowlist check.
        exclude_patterns: Blocklist of regex patterns. Empty list or None skips
            blocklist check.
        verbose: If False, print rejection messages directly (they are suppressed
            by yt-dlp when ``quiet=True``). If True, yt-dlp shows them itself.

    Returns:
        A ``match_filter`` callable accepted by yt-dlp options.
    """
    _excludes = exclude_patterns or []

    def _reject(reason: str) -> str:
        """Print the rejection reason in quiet mode and return it."""
        if not verbose:
            print(f"[download] {reason}")
        return reason

    def _filter(info_dict):
        title = info_dict.get("title", "")

        # Allowlist check: title must match at least one include pattern.
        if patterns and not any(re.search(p, title) for p in patterns):
            return _reject(f"'{title}' doesn't match any artist in the list")

        # Blocklist check: title must not match any exclude pattern.
        for pattern in _excludes:
            if re.search(pattern, title):
                return _reject(f"'{title}' matches exclusion pattern '{pattern}'")

        return None

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
        "thumbnail": f"{output_dir}/%(channel)s/{prefix}%(title)s.%(ext)s",
    }
    return options


def _channel_mode_outtmpl(output_dir: str, config_name: str, prefix: str) -> dict:
    """Build the outtmpl dict for channel-mode downloads.

    Output layout:
      Non-chapter: ``<output>/<config>/<artist>/<title> [<id>].mp3``
      Chapter:     ``<output>/<config>/<artist>/<title> [<id>]/<N> <section>.mp3``

    The video ID is appended to the title to prevent directory/file collisions
    when two different uploads share the same title.

    Args:
        output_dir: Root output directory.
        config_name: Config name(s), e.g. ``"carnatic"`` or
            ``"carnatic,hindustani"`` when multiple configs are combined.
        prefix: Title prefix template (empty string or
            ``"%(release_date|upload_date)s-"`` when ``--prepend-date`` is set).

    Returns:
        Dict with ``"default"``, ``"chapter"``, and ``"thumbnail"`` outtmpl strings.
    """
    base = f"{output_dir}/{config_name}/%(artist,uploader|Unknown)s"
    title_id = "%(title)s [%(id)s]"
    return {
        "default": f"{base}/{prefix}{title_id}.%(ext)s",
        "chapter": f"{base}/{prefix}{title_id}/%(section_number)s %(section_title)s.%(ext)s",
        "thumbnail": f"{base}/{prefix}{title_id}.%(ext)s",
    }


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
) -> tuple[list[Channel], list[str], list[str], dict[str, str]]:
    """Load named configs and configure options for channel download mode.

    Args:
        args: Parsed CLI arguments (``args.channels`` must be set).
        options: yt-dlp options dict to modify in-place.

    Returns:
        Tuple of (channels, urls, config_names, artist_aliases).
        ``artist_aliases`` is the merged alias map from all selected configs.
    """
    if not args.channels:
        build_arg_parser().error("--channels is required when not using --url")

    configs = resolve_configs(args.channels)

    all_channels = [ch for cfg in configs for ch in cfg.channels]
    all_patterns = [p for cfg in configs for p in cfg.title_patterns]
    all_excludes = [p for cfg in configs for p in cfg.exclude_title_patterns]

    # Use video mode if any selected config requests it.
    if any(cfg.output == "video" for cfg in configs):
        configure_video_mode(options)

    if all_patterns or all_excludes:
        options["match_filter"] = make_title_filter(
            all_patterns, exclude_patterns=all_excludes, verbose=args.verbose
        )

    # Record downloaded video IDs so re-runs skip already-downloaded content.
    options["download_archive"] = str(_ARCHIVE_FILE)

    all_urls = [url for ch in all_channels for url in ch.urls]
    all_urls += [url for cfg in configs for url in cfg.urls]
    all_aliases = {k: v for cfg in configs for k, v in cfg.artist_aliases.items()}
    return all_channels, all_urls, [cfg.name for cfg in configs], all_aliases


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
    all_aliases: dict[str, str] = {}
    if args.url:
        capturer, channels, urls = _setup_single_video(args, options)
    else:
        channels, urls, config_names, all_aliases = _setup_channel_mode(args, options)
        if config_names:
            # Switch to <output>/<config-name>/<artist>/<title>/ layout.
            # outtmpl must be updated before YoutubeDL is constructed.
            options["outtmpl"] = _channel_mode_outtmpl(
                args.output_directory,
                ",".join(config_names),
                title_prefix(args.prepend_date),
            )
        print("Fetching channel playlist...")

    ydl = _build_ydl(options, channels, all_aliases, config_names, args.verbose)
    if capturer:
        ydl.add_post_processor(capturer)
    ydl.download(urls)

    if config_names:
        _save_last_downloaded(config_names)

    if capturer:
        run_post_clip(capturer, args.start, args.end)


def _build_ydl(
    options: dict,
    channels: list,
    all_aliases: dict,
    config_names: list,
    verbose: bool,
) -> yt_dlp.YoutubeDL:
    """Build and configure a YoutubeDL instance with all postprocessors.

    Args:
        options: yt-dlp options dict (will be used as-is; deep-copy before calling
            if the caller needs the original intact).
        channels: Channel objects for ID3 metadata lookup.
        all_aliases: Merged artist alias map.
        config_names: Active config names (empty list in single-video mode).
        verbose: Whether verbose output is requested.

    Returns:
        Configured YoutubeDL instance ready to call ``download()``.
    """
    ydl = yt_dlp.YoutubeDL(options)
    if not verbose:
        ydl.add_postprocessor_hook(_make_postprocessor_hook())
    ydl.add_post_processor(
        SetFileMetadata(channels=channels, artist_aliases=all_aliases)
    )
    ydl.add_post_processor(WriteDescriptionAsTxt())
    ydl.add_post_processor(WriteChapterPlaylist())
    ydl.add_post_processor(DeleteUnsplitAudio())
    if config_names:
        channel_map = {ch.handle: ch for ch in channels}
        ydl.add_post_processor(
            InjectArtistMetadata(channel_map, artist_aliases=all_aliases, verbose=verbose),
            when="pre_process",
        )
        # Remove the channel-avatar thumbnail that writethumbnail=True writes for
        # the playlist container entry (no audio file → EmbedThumbnailPP never runs).
        ydl.add_post_processor(DeletePlaylistThumbnail(), when="playlist")
    return ydl


if __name__ == "__main__":
    download_videos()
