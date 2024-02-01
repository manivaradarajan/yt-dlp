Downloads YouTube videos as mp3.

- Keeps the original full converted audio.
- Splits chapters into separate audio files.
- Uses the YouTube video title and pdates id3 tags and thumbnails.

```
usage: download.py [-h] [-o OUTPUT_DIRECTORY] [--split-chapters]

options:
  -h, --help            show this help message and exit
  -o OUTPUT_DIRECTORY, --output-directory OUTPUT_DIRECTORY
                        The directory where the downloaded files will be saved. Default: .
  --split-chapters      Whether to split the extracted audio into chapters (individual audio files). Default: True
```

There's a per-channel way to specify how the id3 tags are extracted from the video.

Uses https://github.com/yt-dlp/yt-dlp.
