"""Download configuration for Desika stotras."""

from config import DownloadConfig

CONFIG = DownloadConfig(
    name="desika-stotras",
    description="Veeraraghavachariar Swami Desika Stotras",
    genre="Stotras",
    urls=["https://www.youtube.com/playlist?list=PLDJF96khF2cAwgi8BOOJMUUMrIBgedqyT"],
    title_patterns=[r"Desika Stotram"],
    output="audio",
)
