#!/usr/bin/env python3
"""One-off script: assign TRCK tags and write an M3U8 playlist for Desika Stotrams.

Ordering follows the traditional LIFCO *Sri Desika Stotramala* parayana sequence
for stotras present in the collection. Stotras absent from the collection are
skipped (their LIFCO slot remains vacant). The five non-LIFCO files are placed
around the core sequence per convention:
  - Desika Vigraha Dhyanam  — opening dhyana sloka (bookend)
  - Desika Dinacharya       \\
  - Desika Ashtakam          > appended after the LIFCO sequence
  - Desika Prapatti         /
  - Desika Mangalasasanam   — closing mangalam sloka (bookend)

Run from the repo root:
    python3 set_stotra_order.py
"""

import pathlib

from mutagen.id3 import ID3, TRCK

MUSIC_DIR = pathlib.Path("out/desika-stotras/Amutham Music")

# Traditional LIFCO parayana order (28 entries).  Stotras absent from the
# collection are listed as None so the sequence is easy to compare against the
# authoritative list.
LIFCO_ORDER = [
    "Hayagriva Stotram",
    "Dasavatara Stotram",
    "Bhagavad Dhyana Sopanam",
    "Abheeti Stavam",
    "Daya Satakam",
    None,  # Varadaraja Panchasat — not downloaded
    "Vairagya Panchakam",
    "Saranagati Deepika",
    "Vegasetu Stotram",
    "Ashtabhuja Ashtakam",
    "Kamasikha Ashtakam",
    "Paramartha Stuti",
    None,  # Devanayaka Panchasat — not downloaded
    None,  # Achyuta Satakam — not downloaded
    "Raghuveera Gadyam",
    "Gopala Vimsati",
    "Dehaleesa Stuti",
    "Sri Stuti",
    "Bhu Stuti",
    "Goda Stuti",
    "Nyasa Dasakam",
    None,  # Nyasa Vimsati — not downloaded
    "Nyasa Tilakam",
    "Sudarshana Ashtakam",
    "Shodasayudha Stotram",
    "Garuda Dandakam",
    None,  # Garuda Panchasat — not downloaded
    "Yatiraja Saptati",
]

# Extras not in the LIFCO 28 but present in the collection.
# Vigraha Dhyanam is the traditional opening dhyana; Mangalasasanam is the
# closing mangalam composed by Kumara Varadacharya (Swami Desikan's son).
OPENING = ["Desika Vigraha Dhyanam"]
MIDDLE_EXTRAS = ["Desika Dinacharya", "Desika Ashtakam", "Desika Prapatti"]
CLOSING = ["Desika Mangalasasanam"]


def build_playlist_order() -> list[str]:
    """Return the full ordered list of titles present in the collection.

    Returns:
        List of title strings in playlist order, all confirmed to exist on disk.
    """
    present = {p.stem for p in MUSIC_DIR.glob("*.mp3")}

    ordered = []
    for title in [t for t in LIFCO_ORDER if t] + OPENING + MIDDLE_EXTRAS + CLOSING:
        if title in present:
            ordered.append(title)
        else:
            print(f"  [skip] '{title}' not found on disk")
    return ordered


def set_track_numbers(ordered: list[str]) -> None:
    """Write sequential TRCK tags (1/N, 2/N, …) to each MP3 in order.

    Args:
        ordered: Title list in desired playback order.
    """
    total = len(ordered)
    for i, title in enumerate(ordered, start=1):
        path = MUSIC_DIR / f"{title}.mp3"
        tags = ID3(path)
        tags["TRCK"] = TRCK(encoding=3, text=f"{i}/{total}")
        tags.save()
        print(f"  {i:>2}/{total}  {title}")


def write_m3u8(ordered: list[str]) -> pathlib.Path:
    """Write an M3U8 playlist file to the music directory.

    Args:
        ordered: Title list in desired playback order.

    Returns:
        Path to the written playlist file.
    """
    playlist_path = MUSIC_DIR / "Desika Stotramala.m3u8"
    lines = ["#EXTM3U"]
    for title in ordered:
        lines.append(f"#EXTINF:-1,{title}")
        lines.append(f"{title}.mp3")
    playlist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return playlist_path


def main() -> None:
    """Build ordering, set TRCK tags, and write the M3U8 playlist."""
    print("Building playlist order...")
    ordered = build_playlist_order()

    print(f"\nSetting track numbers (1–{len(ordered)})...")
    set_track_numbers(ordered)

    playlist_path = write_m3u8(ordered)
    print(f"\nPlaylist written to: {playlist_path}")


if __name__ == "__main__":
    main()
