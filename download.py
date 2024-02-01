import argparse
import re

import yt_dlp

from channel import CarnaticChannel
from metadata_processor import SetFileMetadata

CHANNEL_OUTTMPL = "%(channel)s/%(title)s.%(ext)s"
CHANNEL_VIDEO_OUTTMPL = "%(channel)s/%(title)s/%(title)s.%(ext)s"
CHANNEL_VIDEO_CHAPTER_OUTTMPL = (
    "%(channel)s/%(title)s/%(section_number)s %(section_title)s.%(ext)s"
)

# Specifies matching patterns for titles. Videos matching any of these patterns will be downloaded.
TITLE_PATTERN_LIST = [
    #    r"Ariya[k]?udi",  # Ariyakudi
    r"K\s?V\s?Narayanaswamy",  # KVN
    #    r"Madurai Mani",  # Madurai Mani
]


def title_filter(info_dict):
    """Returns None if info_dict['title'] matches any pattern in TITLE_PATTERN_LIST, or an error string otherwise."""
    title = info_dict.get("title", "")
    for regex_pattern in TITLE_PATTERN_LIST:
        match = re.search(regex_pattern, title)
        if match:
            return None
    return "'%s' doesn't match any artist in the list" % title


# Define options for the download.
# Derived from: ytp-dl's cli_to_api.py tool.
OPTIONS = {
    "extract_flat": "discard_in_playlist",
    "final_ext": "mp3",
    "format": "bestaudio/best",
    "fragment_retries": 10,
    "ignoreerrors": "only_download",
    "merge_output_format": "mp4",
    "outtmpl": {
        "default": CHANNEL_OUTTMPL,
        "chapter": CHANNEL_VIDEO_CHAPTER_OUTTMPL,
        "description": CHANNEL_VIDEO_OUTTMPL,
        "thumbnail": CHANNEL_VIDEO_OUTTMPL,
    },
    "postprocessors": [
        {"format": "jpg", "key": "FFmpegThumbnailsConvertor", "when": "before_dl"},
        {
            "key": "FFmpegExtractAudio",
            "nopostoverwrites": False,
            "preferredcodec": "mp3",
            "preferredquality": "5",
        },
        {
            "add_chapters": True,
            "add_infojson": "if_exists",
            "add_metadata": True,
            "key": "FFmpegMetadata",
        },
        {"already_have_thumbnail": True, "key": "EmbedThumbnail"},
        {"force_keyframes": False, "key": "FFmpegSplitChapters"},
        {"key": "FFmpegConcat", "only_multi_video": True, "when": "playlist"},
    ],
    "retries": 10,
    "writedescription": True,
    "writethumbnail": True,
    "merge_output_format": "mp4",
    "extractaudio": True,
    "audioformat": "mp3",
    "embedthumbnail": True,
    "embedmetadata": True,
    "addmetadata": True,
    "yesplaylist": True,
    "match_filter": title_filter,
}


def download_videos():
    parser = argparse.ArgumentParser()

    # Add the output directory argument
    parser.add_argument(
        "-o",
        "--output-directory",
        default=".",  # Default output directory (current directory)
        help="The directory where the downloaded files will be saved. Default: %(default)s",
    )
    parser.add_argument(
        "--split-chapters",
        action="store_false",
        default=True,
        help="Whether to split the extracted audio into chapters (individual audio files). Default: %(default)s",
    )

    # Parse the arguments
    args = parser.parse_args()

    # Use the output directory
    output_dir = args.output_directory
    print(f"Output will be saved to: {output_dir}")

    options = OPTIONS
    options["outtmpl"] = {
        "default": f"{output_dir}/" + CHANNEL_OUTTMPL,
        "chapter": f"{output_dir}/" + CHANNEL_VIDEO_CHAPTER_OUTTMPL,
        "description": f"{output_dir}/" + CHANNEL_VIDEO_OUTTMPL,
        "thumbnail": f"{output_dir}/" + CHANNEL_VIDEO_OUTTMPL,
    }
    options["split_chapters"]: args.split_chapters

    # Channels to register.
    channels = [
        CarnaticChannel("Carnatic Connect"),
        CarnaticChannel("Balu Karthikeyan"),
        CarnaticChannel("नादभृङ्ग Nādabhṛṅga"),
        CarnaticChannel("Shriram Vasudevan"),
        # The main artist is always at the beginning of the string before "-".
        # Example: "Madurai Mani Iyer | Wedding Concert, 1950’s"
        CarnaticChannel("Vaak", main_artist_match=r"^(.*?) \|"),
    ]

    ydl = yt_dlp.YoutubeDL(options)
    ydl.add_post_processor(SetFileMetadata(channels=channels))
    # Download videos and/or playlists here.
    info_dict = ydl.download(
        [
            "https://www.youtube.com/@BaluKarthikeyan/videos",
            "https://www.youtube.com/@CarnaticConnect/videos",
            "https://www.youtube.com/@Nadabhrnga/videos"
            "https://www.youtube.com/@ShriramVasudevanMusic/videos",
            "https://www.youtube.com/@Vaak_Foundation/videos",
        ]
    )


# TODO: Remove once final
if __name__ == "__main__":
    download_videos()
