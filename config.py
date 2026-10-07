import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("MAKER_BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
DB_PATH = os.getenv("DB_PATH", "data/maker.db")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
PORT = int(os.getenv("PORT", "10000"))
