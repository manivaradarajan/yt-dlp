
from title_processor import SetChapterTitleAsMetadata

import yt_dlp

TEST = True

CHANNEL_OUTTMPL = "%(channel)s/%(title)s.%(ext)s"
CHANNEL_VIDEO_OUTTMPL = "%(channel)s/%(title)s/%(title)s.%(ext)s"
CHANNEL_VIDEO_CHAPTER_OUTTMPL = "%(channel)s/%(title)s/%(section_number)s %(section_title)s.%(ext)s"

TITLE_FILTER_DEFAULT = "K V Narayanaswamy"

CHANNEL_TO_TITLE_DICT_OVERRIDE_DICT = {"BaluKarthikeyan": "KV Narayanaswamy"}

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
        # {
        #     "actions": [
        #         (
        #             yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
        #             "KV Narayanaswamy",
        #             "%(meta_artist)s",
        #         ),
        #         (
        #             yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
        #             "KV Narayanaswamy",
        #             "%(meta_album_artist)s",
        #         ),
        #         (
        #             yt_dlp.postprocessor.metadataparser.MetadataParserPP.interpretter,
        #             "%(title)s",
        #             "%(meta_album)s",
        #         ),
        #     ],
        #     "key": "MetadataParser",
        #     "when": "pre_process",
        # },
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
}

PLAYLIST_OPTIONS = {
    "yesplaylist": True,
}


# Video channels to download
VIDEO_CHANNELS = [
    "BaluKarthikeyan",
    "CarnaticConnect" "Nadabhrnga",
    "ShriramVasudevanMusic",
]

TEST_URL = "https://www.youtube.com/watch?v=CuroQPMKUmY"


def download_playlist(playlist_url, title_filter):
    options = OPTIONS
    options.update(PLAYLIST_OPTIONS)
    options["matchtitle"] = title_filter

    ydl = yt_dlp.YoutubeDL(options)
    ydl.add_post_processor(SetChapterTitleAsMetadata())
    ydl.download([playlist_url])


# TODO: Remove once final
if __name__ == "__main__":
    download_playlist(TEST_URL, TITLE_FILTER_DEFAULT)
