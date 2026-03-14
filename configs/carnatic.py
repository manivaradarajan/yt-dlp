"""Download configuration for Carnatic classical music channels."""

from channel import Channel
from config import DownloadConfig

# Vaak titles use "Artist | Concert title" rather than "Artist - Concert title".
VAAK = Channel(handle="@Vaak_Foundation", artist_match=[r"^(.*?) \|"])

CONFIG = DownloadConfig(
    name="carnatic",
    description="Carnatic classical music: Ariyakudi, KVN and Madurai Mani Iyer concerts.",
    genre="Carnatic",
    channels=["@CarnaticConnect", "@BaluKarthikeyan", "@Nadabhrnga", "@ShriramVasudevanMusic", VAAK],
    title_patterns=[
        r"Ariya[k]?udi",
        r"Madurai Mani",
    ],
    output="audio",
)
