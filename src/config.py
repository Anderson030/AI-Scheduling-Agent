import os
from dotenv import load_dotenv
import pytz

load_dotenv()

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Google Calendar
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")

# Settings
TIMEZONE_STR = os.getenv("TIMEZONE", "America/Bogota")
TIMEZONE = pytz.timezone(TIMEZONE_STR)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./appointments.db")

# Validation
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY not found in environment variables.")
if not TELEGRAM_BOT_TOKEN:
    print("Warning: TELEGRAM_BOT_TOKEN not found in environment variables.")
