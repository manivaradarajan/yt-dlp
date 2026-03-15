"""Download configuration dataclass.

``DownloadConfig`` bundles a set of channels with title-filter patterns and an
output mode into a self-contained, named configuration.  It is deliberately
separate from ``channel.py`` — a ``Channel`` models a single YouTube source,
while a ``DownloadConfig`` is a higher-level job descriptor that may reference
many channels.
"""

import dataclasses
from dataclasses import dataclass, field
from typing import Literal

from channel import Channel


@dataclass(frozen=True)
class DownloadConfig:
    """A named, self-contained download configuration.

    Bundles a list of channels with title-filter patterns and an output mode
    into everything needed to run a complete yt-dlp session.

    Channels can be specified as bare handle strings (e.g. ``"@CarnaticConnect"``)
    or as full ``Channel`` objects.  Bare strings and ``Channel`` objects with
    ``genre=None`` inherit the config-level ``genre`` automatically.

    Example::

        CONFIG = DownloadConfig(
            name="carnatic",
            description="...",
            genre="Carnatic",
            channels=[
                "@CarnaticConnect",
                "@BaluKarthikeyan",
                Channel(handle="@Vaak_Foundation", artist_match=[r"^(.*?) \\|"]),
            ],
            title_patterns=[r"Ariyakudi"],
            output="audio",
        )
    """

    name: str
    """Machine-readable key used with ``--channels``."""

    description: str
    """Human-readable summary shown by ``--list-channels``."""

    genre: str
    """Default ID3 genre tag for channels that don't declare their own."""

    title_patterns: list[str]
    """Regex filters for video titles.  Empty list means no filtering."""

    output: Literal["audio", "video"]
    """Whether to extract MP3 audio or keep the full video file."""

    channels: list[Channel | str] = field(default_factory=list)
    """Channels to download, specified as bare handle strings or ``Channel`` objects.

    ``__post_init__`` coerces bare strings to ``Channel`` objects, filling in
    ``genre`` from the config level.  ``Channel`` objects with ``genre=None``
    also inherit the config genre.  Use this when you want custom ID3 tag
    extraction (artist name, track number, etc.).
    """

    artist_aliases: dict[str, str] = field(default_factory=dict)
    """Mapping from variant artist names to their canonical form.

    Keys are post-normalization names (what ``normalize_initials`` produces).
    Values are the canonical spelling to use for folder names and ID3 tags.

    Example::

        artist_aliases={"Narayanaswami": "Narayanaswamy"}
    """

    urls: list[str] = field(default_factory=list)
    """Direct playlist or channel URLs to download, without a Channel handler.

    Use this when you have a playlist URL and don't need custom ID3 extraction.
    Videos downloaded via ``urls`` will still have yt-dlp's built-in metadata,
    but won't go through ``SetFileMetadata`` artist/track extraction.

    Example::

        urls=["https://www.youtube.com/playlist?list=PLxxx"]
    """

    def __post_init__(self) -> None:
        """Resolve channels: coerce bare strings and fill in missing genres.

        - Bare handle strings become ``Channel(handle=s, genre=self.genre)``.
        - ``Channel`` objects with ``genre=None`` get ``self.genre`` substituted in.
        - ``Channel`` objects with an explicit genre are left unchanged.
        """
        resolved = []
        for ch in self.channels:
            if isinstance(ch, str):
                resolved.append(Channel(handle=ch, genre=self.genre))
            elif ch.genre is None:
                resolved.append(dataclasses.replace(ch, genre=self.genre))
            else:
                resolved.append(ch)
        object.__setattr__(self, "channels", resolved)
