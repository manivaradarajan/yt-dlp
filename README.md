# yt-dlp Carnatic Downloader

Downloads YouTube videos from Carnatic music channels as MP3, with chapter
splitting and ID3 tag extraction. Also supports downloading individual videos
or clips as audio or video.

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if you
don't have it. The installation page covers all platforms; on Linux/macOS the
one-liner is:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Create the venv and install all dependencies:

```bash
uv sync
```

Activate the venv (needed before running `python` directly):

```bash
# Linux / macOS
source .venv/bin/activate

# Windows
.venv\Scripts\activate
```

Requires `ffmpeg` and `node` on your PATH. Install via your system package
manager or the official downloads:

- **ffmpeg**: <https://ffmpeg.org/download.html>
- **Node.js**: <https://nodejs.org/en/download>

## Channel downloads

List available configurations:

```bash
python download.py --list-channels
```

Download one or more named configs:

```bash
python download.py --channels carnatic [-o OUTPUT_DIRECTORY]
python download.py --channels carnatic,hindustani -o /tmp/music
```

Output is organised as `OUTPUT_DIRECTORY/<config-name>/<artist>/<title> [<id>]/`.
The YouTube video ID is included in the name to prevent collisions when two
uploads share the same title. Each video produces an MP3, embedded thumbnail,
and a `.txt` sidecar with the YouTube description. If the video has chapters,
each chapter is split into a separate MP3 inside the album directory, alongside
an M3U8 playlist.

### Incremental downloads

Downloaded video IDs are recorded in `~/.yt-dlp-archive.txt`. On subsequent
runs, already-downloaded videos are skipped automatically. To force a full
re-download, delete the archive:

```bash
rm ~/.yt-dlp-archive.txt        # Linux / macOS
del %USERPROFILE%\.yt-dlp-archive.txt   # Windows
```

## Writing a config

Configs live in `configs/`. Each file exports a `CONFIG` object and is discovered
automatically — no other file needs to change.

**Channel handles** — download from one or more YouTube channels with artist/ID3 tag extraction:

```python
# configs/hindustani.py
from channel import Channel
from config import DownloadConfig

CONFIG = DownloadConfig(
    name="hindustani",
    description="Hindustani classical music",
    genre="Hindustani",          # inherited by all channels below
    channels=["@SomeChannel", "@AnotherChannel"],
    title_patterns=[             # empty list = download all videos
        r"Ravi Shankar",
        r"Ali Akbar",
    ],
    output="audio",
)
```

**Direct playlist URLs** — download a specific playlist without a channel handle:

```python
# configs/my_playlist.py
from config import DownloadConfig

CONFIG = DownloadConfig(
    name="my-playlist",
    description="A curated playlist",
    genre="Classical",
    urls=["https://www.youtube.com/playlist?list=PLxxxx"],
    title_patterns=[],
    output="audio",
)
```

**Multiple playlists from one channel** — use `playlist_urls` on a `Channel` to target
specific playlists instead of the channel's full `/videos` page:

```python
from channel import Channel
from config import DownloadConfig

CONFIG = DownloadConfig(
    name="hindustani",
    description="Selected playlists",
    genre="Hindustani",
    channels=[
        Channel(
            handle="@SomeChannel",
            playlist_urls=[
                "https://www.youtube.com/playlist?list=PLaaa",
                "https://www.youtube.com/playlist?list=PLbbb",
            ],
        ),
    ],
    title_patterns=[],
    output="audio",
)
```

**Custom artist pattern** — for channels that use `"Artist | Concert"` instead of `"Artist - Concert"`:

```python
from channel import Channel
from config import DownloadConfig

CUSTOM = Channel(handle="@SomeChannel", artist_match=[r"^(.*?) \|"])

CONFIG = DownloadConfig(
    name="hindustani",
    description="...",
    genre="Hindustani",
    channels=["@NormalChannel", CUSTOM],
    title_patterns=[],
    output="audio",
)
```

**Artist aliases** — map variant spellings to a canonical name used in folder names and ID3 tags:

```python
CONFIG = DownloadConfig(
    name="carnatic",
    ...
    artist_aliases={
        "Narayanaswami": "Narayanaswamy",   # post-normalization key → canonical value
    },
)
```

Aliases are applied after `normalize_initials()` runs on the extracted name, so keys
should use the merged-initials form (e.g. `"KV Narayanaswamy"`, not `"K V Narayanaswamy"`).

The `genre` on `DownloadConfig` is inherited by all channels listed as bare strings.
A full `Channel(...)` object is only needed when overriding `artist_match` or
`playlist_urls`.

## Single video download

```bash
python download.py --url URL --audio|--video [options]
```

`--audio` or `--video` is required when using `--url`.

| Flag | Description |
|------|-------------|
| `--url URL` | YouTube video URL to download |
| `--audio` | Extract audio to MP3 |
| `--video` | Download video file |
| `--start HH:MM:SS` | Clip start time |
| `--end HH:MM:SS` | Clip end time |
| `--quality HEIGHT` | Cap resolution in pixels, e.g. `1080` or `720` (requires `--video`) |
| `--prepend-date` | Prefix output filename with `YYYYMMDD-` (uses release date) |
| `-o OUTPUT_DIRECTORY` | Output directory (default: current directory) |

### Examples

```bash
# Download a video as MP3
python download.py --url "https://www.youtube.com/watch?v=XXXX" --audio -o out/

# Clip a time range from a video, save as MP3
python download.py --url "https://www.youtube.com/watch?v=XXXX" \
    --audio --start 00:04:22 --end 00:13:45 -o out/

# Download a clip as 1080p video with date-prefixed filename
python download.py --url "https://www.youtube.com/watch?v=XXXX" \
    --video --quality 1080 --start 00:04:22 --end 00:13:45 --prepend-date -o out/
```

### Live / DVR streams

For past live streams, `--start`/`--end` cannot clip during download (YouTube's
DASH/DVR format doesn't support mid-stream seeking). The script detects this
automatically, downloads the full stream first, then clips with ffmpeg.

## Verbosity

By default the output shows a live progress bar per file and a `[postprocess]`
line for each slow FFmpeg stage (audio extraction, chapter splitting, thumbnail
embedding). Pass `--verbose` to see yt-dlp's full output instead:

```bash
python download.py --channels carnatic --verbose
```

## Passing extra yt-dlp options

`--yt-dlp-opt KEY=VALUE` merges any option from the [yt-dlp Python API](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp) into the download options. Values are JSON-parsed, so numbers and booleans work as expected. The flag can be repeated.

```bash
python download.py --channels carnatic --yt-dlp-opt sleep_interval=3
```

### Rate limiting

If YouTube rate-limits your session you'll see:

> The current session has been rate-limited by YouTube for up to an hour.

Add a delay between videos and between requests within each video:

```bash
python download.py --channels carnatic \
    --yt-dlp-opt sleep_interval=3 \
    --yt-dlp-opt sleep_interval_requests=1
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for architecture and developer notes.
