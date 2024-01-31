import re

import yt_dlp

from title_processor import SetFileMetadata

CHANNEL_OUTTMPL = "%(channel)s/%(title)s.%(ext)s"
CHANNEL_VIDEO_OUTTMPL = "%(channel)s/%(title)s/%(title)s.%(ext)s"
CHANNEL_VIDEO_CHAPTER_OUTTMPL = (
    "%(channel)s/%(title)s/%(section_number)s %(section_title)s.%(ext)s"
)


TITLE_PATTERN_LIST = [
    r"Ariya[k]?udi",          # Ariyakudi
    r"K\s?V\s?Narayanaswamy", # KVN
    r"Madurai Mani",          # Madurai Mani
]


def any_regex_matches(input_string, regex_list):
    for regex_pattern in regex_list:
        match = re.search(regex_pattern, input_string)
        if match:
            return None
    return 'Title doesn\'t match any specified artist'


def title_filter(info_dict):
    title = info_dict.get("title", "")
    return any_regex_matches(title, TITLE_PATTERN_LIST)


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
        "infojson": CHANNEL_VIDEO_OUTTMPL,
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
    "writeinfojson": True,
    "writethumbnail": True,
    "writedescription": True,
    "writeinfojson": True,
    "writethumbnail": True,
    "split_chapters": True,
    "merge_output_format": "mp4",
    "extractaudio": True,
    "audioformat": "mp3",
    "embedthumbnail": True,
    "embedmetadata": True,
    "addmetadata": True,
    "yesplaylist": True,
    "match_filter": title_filter,
}


def download_playlist():
    ydl = yt_dlp.YoutubeDL(OPTIONS)
    ydl.add_post_processor(SetFileMetadata())
    # Download the video and retrieve information
    info_dict = ydl.download([
        "https://www.youtube.com/@BaluKarthikeyan/videos",
        "https://www.youtube.com/@CarnaticConnect/videos",
        "https://www.youtube.com/@Nadabhrnga/videos"
        "https://www.youtube.com/@ShriramVasudevanMusic/videos",
        "https://www.youtube.com/@Vaak_Foundation/videos",
    ])


# TODO: Remove once final
if __name__ == "__main__":
    download_playlist()
