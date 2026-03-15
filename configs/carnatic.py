"""Download configuration for Carnatic classical music channels."""

from channel import Channel
from config import DownloadConfig

# CarnaticConnect uses " | " as separator in video titles:
#   "Artist | Venue | Date"
# (yt-dlp sanitises | → ｜ in filenames, but the title string has plain |.)
# The default r"^(.*?) -" only handles dash-separated titles, so we add
# the pipe pattern as well.
CARNATIC_CONNECT = Channel(
    handle="@CarnaticConnect",
    artist_match=[r"^(.*?) \|", r"^(.*?) -"],
)

# Vaak titles use "Artist | Concert title" rather than "Artist - Concert title".
VAAK = Channel(handle="@Vaak_Foundation", artist_match=[r"^(.*?) \|"])

CONFIG = DownloadConfig(
    name="carnatic",
    description="Carnatic classical music",
    genre="Carnatic",
    channels=[CARNATIC_CONNECT, "@BaluKarthikeyan", "@Nadabhrnga", "@ShriramVasudevanMusic", VAAK],
    title_patterns=[
        r"Ariya[k]?udi",
        r"Madurai Mani",
        r"Semmangudi",
        r"K\s*V\s*N",
        r"T\s*V\s*S",
        r"Musiri",
        r"R\s*K\s+Srik",
        r"M\s*S\s*G",
    ],
    output="audio",
)
