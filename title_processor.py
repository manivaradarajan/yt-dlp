import os
import re

import yt_dlp
from mutagen import id3
from yt_dlp.postprocessor.common import PostProcessor

from channel_metadata import CarnaticConnectMetadata


class SetFileMetadata(PostProcessor):
    channel_metadata = {}

    def __init__(self, downloader=None, **kwargs):
        super(SetFileMetadata, self).__init__(downloader, **kwargs)
        md = CarnaticConnectMetadata()
        self.channel_metadata[md.channel] = md

    def run(self, info):
        if info['ext'] == 'mp3':
            if info['channel'] in self.channel_metadata.keys():
                metadata = self.channel_metadata[info['channel']]
                metadata.set_metadata(info['filepath'], info['title'])

                # Extracted chapters are available in 'chapters' field
                for i, chapter in enumerate(info['chapters']):
                    metadata.set_metadata(chapter['filepath'], info['title'], is_chapter=True)

        return [], info
