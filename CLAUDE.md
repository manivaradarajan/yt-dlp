# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A YouTube to MP3 downloader for Carnatic classical music channels. Downloads videos, extracts audio, splits by chapters, and sets ID3 metadata tags.

## Commands

**Run the downloader:**
```bash
python download.py [-o OUTPUT_DIRECTORY] [--split-chapters]
```

**Format code:**
```bash
black *.py
```

**Type check:**
```bash
mypy *.py
```

**Build with Bazel:**
```bash
bazel build //download
```

There is no test suite.

## Architecture

The pipeline has four stages:

1. **Config** (`config.py`) — defines `URLS` (YouTube channel URLs to download) and `TITLE_PATTERNS` (regex filters to select specific videos by title).

2. **Download** (`download.py`) — CLI entry point. Configures yt-dlp with output templates and postprocessors (thumbnail conversion, MP3 extraction, chapter splitting). Calls `download_videos()` with registered channel handlers.

3. **Channel metadata** (`channel.py`) — `Channel` is an ABC; `CarnaticChannel` is the concrete implementation. Each channel instance holds regex patterns for extracting artist, track number, and year from filenames. The `song_metadata()` method returns a `SongMetadata` dataclass.

4. **Postprocessing** (`metadata_processor.py`) — `SetFileMetadata` is a yt-dlp `PostProcessor`. After download it iterates over the main file and any chapter files, looks up the registered channel handler, and writes ID3 tags via mutagen.

**Extending to a new channel:** Subclass `Channel` (or instantiate `CarnaticChannel` with custom regex parameters), register it in `download.py`, and add its URL to `config.py`.
