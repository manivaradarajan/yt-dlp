# Development Guide

## Architecture

| File | Role |
|------|------|
| `channel.py` | `Channel` dataclass — handle, genre, artist/track extraction, playlist URLs |
| `config.py` | `DownloadConfig` dataclass — named job bundling channels, filters, and output mode |
| `configs/carnatic.py` | Carnatic music download config; exports `CONFIG: DownloadConfig` |
| `download.py` | CLI entry point; discovers configs, builds yt-dlp options, orchestrates the run |
| `postprocessors.py` | yt-dlp `PostProcessor` subclasses for the download pipeline |
| `clipping.py` | Broadcast detection and time-range clipping for single-video downloads |
| `metadata_processor.py` | `SetFileMetadata` postprocessor — writes ID3 tags via mutagen |

The pipeline has four stages:

1. **Config** (`configs/*.py`) — each file exports a `CONFIG: DownloadConfig` object bundling channels, title filters, and output mode.
2. **Download** (`download.py`) — CLI entry point. Discovers configs automatically, configures yt-dlp with postprocessors (thumbnail conversion, MP3 extraction, chapter splitting), and dispatches to channel or single-video mode.
3. **Channel metadata** (`channel.py`) — `Channel` holds regex patterns for extracting artist, track number, and year from filenames. `song_metadata()` returns a `SongMetadata` dataclass.
4. **Postprocessing** — two postprocessor files handle the pipeline after download:
   - `postprocessors.py` — `WriteDescriptionAsTxt`, `WriteChapterPlaylist`, `DeleteUnsplitAudio`, `DeletePlaylistThumbnail`, `InjectArtistMetadata`
   - `metadata_processor.py` — `SetFileMetadata` writes ID3 tags via mutagen

## Logging design

`quiet=True` is set globally to suppress yt-dlp's chatty info output. Three
mechanisms restore the messages that matter:

| Mechanism | What it shows |
|-----------|---------------|
| `_QuietLogger` | Warnings and errors — yt-dlp routes these through the logger interface instead of `to_screen` when a custom logger is set |
| `_make_progress_hook()` | Live per-file progress bar (filename + coloured block bar + % + speed + ETA); updates in place via `\r`. Only shown when `total_bytes` is known — estimates are suppressed as unreliable. |
| `_make_postprocessor_hook()` | `[postprocess]` line when slow FFmpeg stages begin: audio extraction, chapter splitting, thumbnail embedding |
| `print()` in `make_title_filter` | Filter rejections — yt-dlp suppresses these via `to_screen` in quiet mode, so the filter prints them directly |

`--verbose` bypasses all of this: it sets `quiet=False, verbose=True` on yt-dlp
and skips the custom logger and progress hooks, restoring full yt-dlp output.

### Caveats

- **DASH video+audio streams**: The progress hook fires separately for the video
  stream and the audio stream before they are merged, so the user sees two
  progress bars instead of one. This doesn't occur for audio-only downloads (the
  common case).
- **Early stopping**: `download_archive` skips archived videos but still scans
  the full playlist. To stop as soon as the first archived video is hit (useful
  for large single-channel runs), add `--yt-dlp-opt break_on_existing=true`.
  Avoid this with multiple channels or playlists — it may prevent later URLs
  from being processed.

## Adding a new download config

A config is a single Python file in `configs/` that exports one `CONFIG:
DownloadConfig` object. No changes to `download.py` are needed — it discovers
all `configs/*.py` files automatically.

**Create `configs/myconfig.py`:**

```python
"""Download configuration for my new config."""
from channel import Channel
from config import DownloadConfig

# Only channels that need a custom artist_match require a full Channel() object.
# Pipe-separated titles: "Artist | Concert title"
CUSTOM_CH = Channel(handle="@CustomHandle", artist_match=[r"^(.*?) \|"])

CONFIG = DownloadConfig(
    name="myconfig",             # used with --channels myconfig
    description="Short description shown by --list-channels",
    genre="Hindustani",          # default ID3 genre; inherited by all channels
    channels=[
        "@SimpleChannel",        # bare string: uses genre above, default artist_match
        "@AnotherChannel",
        CUSTOM_CH,               # full Channel object: custom artist_match
    ],
    urls=[                       # optional: direct playlist URLs (no Channel handler)
        "https://www.youtube.com/playlist?list=PLxxxx",
    ],
    title_patterns=[             # empty list = download everything
        r"Artist Name",
    ],
    output="audio",              # "audio" extracts MP3; "video" keeps the video file
)
```

`channels` and `urls` can be used independently or together. Videos from `urls` use
yt-dlp's built-in metadata only — they don't go through `SetFileMetadata`
artist/track extraction.

**Verify:**

```bash
python download.py --list-channels
# Expected: "myconfig  Short description shown by --list-channels"

python download.py --channels myconfig -o /tmp/test
```

## Dependency management

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`.
[uv](https://docs.astral.sh/uv/) manages both the venv and the lockfile.

```
[project.dependencies]   ← runtime deps (yt-dlp, mutagen)
[dependency-groups.dev]  ← dev tools (black, mypy, pytest)
```

**Install or sync the venv** (after pulling or changing `pyproject.toml`):

```bash
uv sync
```

**Add a new runtime dependency:**

```bash
uv add <package>          # updates pyproject.toml and uv.lock
```

**Add a new dev-only tool:**

```bash
uv add --group dev <package>
```

**Upgrade all packages to the latest allowed versions:**

```bash
uv sync --upgrade
```

Commit both `pyproject.toml` and `uv.lock` so any checkout reproduces the same environment with a single `uv sync`.

## Running tests

```bash
uv run pytest
```

Tests cover pure helper functions and dataclass logic — no network calls or file I/O:

- `tests/test_channel.py` — `Channel.song_metadata()`, `Channel.urls`, `normalize_initials()`
- `tests/test_download.py` — progress helpers (`_format_speed`, `_format_eta`, `_format_size`, `_make_bar`, `_build_progress_line`, `_strip_ansi`), `parse_time` (clipping), `make_title_filter`, `video_format`, `configure_video_mode`, `load_configs`, `resolve_configs`, `WriteChapterPlaylist`, `DeleteUnsplitAudio`, `WriteDescriptionAsTxt`, `InjectArtistMetadata`
- `tests/test_metadata_processor.py` — `_normalize_handle`, `SetFileMetadata` chapters-None guard

yt-dlp download behaviour, ffmpeg postprocessing, and mutagen tag writing are not covered by the test suite.

## One-off collection scripts

Scripts in the repo root that are **not part of the downloader** — they were
written to fix up a specific downloaded collection and are kept as reference:

| File | Purpose |
|------|---------|
| `fix_stotra_tags.py` | Renames Desika Stotra MP3s and rewrites their ID3 title/artist tags using the canonical names in `stotras.csv` |
| `set_stotra_order.py` | Assigns sequential TRCK tags and writes `Desika Stotramala.m3u8` based on the traditional LIFCO parayana order |
| `stotras.csv` | Mapping of original (YouTube) titles → canonical Sanskrit titles for the Desika Stotra collection |

## Formatting and type checking

```bash
uv run black *.py configs/*.py      # format
uv run mypy *.py configs/*.py       # type check
```
