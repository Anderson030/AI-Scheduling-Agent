import os
from dotenv import load_dotenv
import pytz

load_dotenv()

# Normalizar funciones de limpieza
def clean_env_var(val):
    if not val: return None
    import re
    # Eliminar cualquier cosa que no sea un carácter alfanumérico o símbolos válidos en keys
    return re.sub(r'[\s\t\n\r"\' ]', '', val).strip()

# API Keys
OPENAI_API_KEY = clean_env_var(os.getenv("OPENAI_API_KEY"))
TELEGRAM_BOT_TOKEN = clean_env_var(os.getenv("TELEGRAM_BOT_TOKEN"))
RAW_WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_URL = RAW_WEBHOOK_URL.rstrip('/') if RAW_WEBHOOK_URL else None

# Google Calendar
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON") 
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")
GOOGLE_CLIENT_ID = clean_env_var(os.getenv("GOOGLE_CLIENT_ID"))
GOOGLE_CLIENT_SECRET = clean_env_var(os.getenv("GOOGLE_CLIENT_SECRET"))

# Settings
TIMEZONE_STR = os.getenv("TIMEZONE", "America/Bogota")
TIMEZONE = pytz.timezone(TIMEZONE_STR)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./appointments.db")

# Validation
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY not found in environment variables.")
if not TELEGRAM_BOT_TOKEN:
    print("Warning: TELEGRAM_BOT_TOKEN not found in environment variables.")
