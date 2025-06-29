import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_URL = os.getenv("SQLALCHEMY_DATABASE_URL")