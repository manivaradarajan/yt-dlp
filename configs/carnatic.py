"""Download configuration for Carnatic classical music channels."""

from channel import Channel
from config import DownloadConfig

# CarnaticConnect titles appear in three formats:
#   "Artist | Venue | Date"  → pipe pattern
#   "Artist - Concert"       → dash pattern
#   "Artist Name"            → no separator; title IS the artist name
#                              (matched by letters-only fallback)
# (yt-dlp sanitises | → ｜ in filenames, but the title string uses plain |.)
CARNATIC_CONNECT = Channel(
    handle="@CarnaticConnect",
    artist_match=[r"^(.*?) \|", r"^(.*?) -", r"^([A-Za-z .]+)$"],
)

# Vaak titles use "Artist | Concert title" rather than "Artist - Concert title".
VAAK = Channel(handle="@Vaak_Foundation", artist_match=[r"^(.*?) \|"])

CONFIG = DownloadConfig(
    name="carnatic",
    description="Carnatic classical music",
    genre="Carnatic",
    channels=[CARNATIC_CONNECT, "@BaluKarthikeyan", "@Nadabhrnga", "@ShriramVasudevanMusic", VAAK],
    title_patterns=[
        r"Alathur",
        r"Ariya[k]?udi",
        r"Brinda",
        r"K\s*V\s*N",
        r"M\s*S\s*G",
        r"Madurai Mani",
        r"M\s*S\s*G",
        r"Musiri",
        r"Doraiswamy Iyengar",
        r"R\s*K\s+Srik",
        r"Rama?nad\s+Krishnan",
        r"Semmangudi",
        r"T\s*V\s*S",
    ],
    exclude_title_patterns=[
        r"Chitti Babu",
        r"MD Ramanathan",
        r"Voleti",
    ],
    output="audio",
    artist_aliases={
        "Ariyakkudi Ramanuja Iyengar": "Ariyakudi Ramanuja Iyengar",
        "Palghat KV Narayanaswamy": "KV Narayanaswamy",
        "Ramanad Krishnan": "Ramnad Krishnan",
        "TV Shankaranarayanan": "TV Sankaranarayanan",
    },
)
