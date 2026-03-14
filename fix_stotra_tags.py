#!/usr/bin/env python3
"""One-off script: rename Desika Stotra MP3s and fix their ID3 tags.

Reads stotras.csv for Original→Canonical title mappings, then for each entry:
  - Updates TIT2 (title) and TPE1/TPE2 (artist) ID3 tags.
  - Renames the file to <Canonical>.mp3 in the same directory.

Run from the repo root:
    python3 fix_stotra_tags.py
"""

import csv
import pathlib

from mutagen.id3 import ID3, TPE1, TPE2, TIT2

ARTIST = "Veeraraghavacharya"
MUSIC_DIR = pathlib.Path("out/desika-stotras/Amutham Music")
CSV_PATH = pathlib.Path("stotras.csv")


def load_mapping(csv_path: pathlib.Path) -> list[tuple[str, str]]:
    """Load Original→Canonical title pairs from the CSV.

    Args:
        csv_path: Path to the CSV file with 'Original' and 'Canonical' columns.

    Returns:
        List of (original_title, canonical_title) tuples, skipping blank rows.
    """
    with csv_path.open(newline="", encoding="utf-8") as f:
        return [
            (row["Original"], row["Canonical"])
            for row in csv.DictReader(f)
            if row["Original"] and row["Canonical"]
        ]


def update_tags(mp3_path: pathlib.Path, title: str, artist: str) -> None:
    """Overwrite the title and artist ID3 tags on an MP3 file in-place.

    Args:
        mp3_path: Path to the MP3 file.
        title: New value for TIT2 (title).
        artist: New value for TPE1 and TPE2 (artist / album artist).
    """
    tags = ID3(mp3_path)
    tags["TIT2"] = TIT2(encoding=3, text=title)
    tags["TPE1"] = TPE1(encoding=3, text=artist)
    tags["TPE2"] = TPE2(encoding=3, text=artist)
    tags.save()


def rename_mp3(mp3_path: pathlib.Path, canonical: str) -> pathlib.Path:
    """Rename an MP3 to <canonical>.mp3 in the same directory.

    Args:
        mp3_path: Current path.
        canonical: Desired stem (no extension).

    Returns:
        The new path after renaming.
    """
    new_path = mp3_path.with_name(f"{canonical}.mp3")
    mp3_path.rename(new_path)
    return new_path


def main() -> None:
    """Process all mappings: update tags and rename each MP3."""
    mapping = load_mapping(CSV_PATH)
    not_found = []

    for original, canonical in mapping:
        mp3_path = MUSIC_DIR / f"{original}.mp3"
        if not mp3_path.exists():
            not_found.append(original)
            continue

        update_tags(mp3_path, title=canonical, artist=ARTIST)
        new_path = rename_mp3(mp3_path, canonical)
        print(f"{original}\n  → {new_path.name}\n")

    if not_found:
        print(f"Not found ({len(not_found)}):")
        for title in not_found:
            print(f"  {title}")


if __name__ == "__main__":
    main()
