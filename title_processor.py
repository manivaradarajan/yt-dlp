import os
import re
import yt_dlp

from mutagen import id3
from yt_dlp.postprocessor.common import PostProcessor

NUMERIC_PREFIX_REGEXP = r'^[\s0-9\. ]+'

class SetChapterTitleAsMetadata(PostProcessor):
    def __init__(self, downloader=None, **kwargs):
        super(SetChapterTitleAsMetadata, self).__init__(downloader, **kwargs)

    def run(self, info):
        if info['ext'] == 'mp3':
            # Extracted chapters are available in 'chapters' field
            for i, chapter in enumerate(info['chapters']):
                id3_tags = id3.ID3(chapter['filepath'])

                # Extract the filename from the full path
                filename = os.path.basename(chapter['filepath'])
                # Strip off the file extension
                filename_no_ext, _ = os.path.splitext(filename)
                song_title = re.sub(NUMERIC_PREFIX_REGEXP, '', filename_no_ext)

                # Set ID3 tags
                id3_tags.add(id3.TIT2(encoding=3, text=song_title))
                # TODO
                #id3_tags.add(id3.TPE1(encoding=3, text=artist))
                #id3_tags.add(id3.TALB(encoding=3, text=album))
                id3_tags.save()

        return [], info
