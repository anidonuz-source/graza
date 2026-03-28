import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]


    MAX_PHOTO_SIZE = 20 * 1024 * 1024  # 20 MB
    MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50 MB
    MAX_GIF_SIZE = 20 * 1024 * 1024  # 20 MB


# Config obyektini yaratish
config = Config()