# yt-dlp Carnatic Downloader

Downloads YouTube videos from Carnatic music channels as MP3, with chapter
splitting and ID3 tag extraction. Also supports downloading individual videos
or clips as audio or video.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install yt-dlp mutagen black mypy
```

Requires `ffmpeg` and `node` on your PATH:

```bash
brew install ffmpeg node
```

## Channel downloads

Edit `config.py` to configure which channels and artists to download, then:

```bash
python download.py [-o OUTPUT_DIRECTORY] [--split-chapters]
```

Output is organised as `OUTPUT_DIRECTORY/<channel>/<title>/`. Each video
produces an MP3, embedded thumbnail, and a `.txt` sidecar with the YouTube
description. If the video has chapters, each chapter is split into a separate
MP3.

## Single video download

```bash
python download.py --url URL [options]
```

| Flag | Description |
|------|-------------|
| `--url URL` | YouTube video URL to download |
| `--start HH:MM:SS` | Clip start time |
| `--end HH:MM:SS` | Clip end time |
| `--video` | Download video file instead of extracting audio to MP3 |
| `--quality HEIGHT` | Cap resolution in pixels, e.g. `1080` or `720` (implies `--video`) |
| `--prepend-date` | Prefix output filename with `YYYYMMDD-` (uses release date) |
| `-o OUTPUT_DIRECTORY` | Output directory (default: current directory) |

### Examples

```bash
# Download a video as MP3
python download.py --url "https://www.youtube.com/watch?v=XXXX" -o out/

# Clip a time range from a video, save as MP3
python download.py --url "https://www.youtube.com/watch?v=XXXX" \
    --start 00:04:22 --end 00:13:45 -o out/

# Download a clip as 1080p video with date-prefixed filename
python download.py --url "https://www.youtube.com/watch?v=XXXX" \
    --start 00:04:22 --end 00:13:45 --quality 1080 --prepend-date -o out/
```

### Live / DVR streams

For past live streams, `--start`/`--end` cannot clip during download (YouTube's
DASH/DVR format doesn't support mid-stream seeking). The script detects this
automatically, downloads the full stream first, then clips with ffmpeg.

## Development

```bash
black *.py      # format
mypy *.py       # type check
```

## Architecture

| File | Role |
|------|------|
| `config.py` | Channel URLs and title regex filters |
| `download.py` | CLI entry point; configures yt-dlp and postprocessors |
| `channel.py` | Per-channel metadata extraction (`CarnaticChannel`) |
| `metadata_processor.py` | `SetFileMetadata` postprocessor — writes ID3 tags via mutagen |

**To add a new channel:** subclass `Channel` or instantiate `CarnaticChannel`
with custom regex parameters, register it in `download.py`, and add its URL
to `config.py`.
