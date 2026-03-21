import os
import sys
from dotenv import load_dotenv

# Add src to path
sys.path.append(os.getcwd())

load_dotenv()

from src.config import GEMINI_API_KEY
from src.database import SessionLocal, init_db, UserAuth, USE_SQLITE, DATABASE_URL
import google.generativeai as genai


def test_gemini():
    print(f"--- Testing Gemini API ---")
    print(f"API Key (first 10 chars): {GEMINI_API_KEY[:10] if GEMINI_API_KEY else 'None'}...")
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content("Responde solo 'OK' en una palabra.")
        print(f"Gemini Success: {response.text.strip()}")
        return True
    except Exception as e:
        print(f"Gemini Error: {e}")
        return False


def test_db():
    print(f"\n--- Testing Database Connection ---")
    print(f"DATABASE_URL: {DATABASE_URL}")
    print(f"USE_SQLITE: {USE_SQLITE}")
    try:
        init_db()
        db = SessionLocal()
        count = db.query(UserAuth).count()
        print(f"Database Success: Found {count} authenticated users.")
        db.close()
        return True
    except Exception as e:
        print(f"Database Error: {e}")
        return False


if __name__ == "__main__":
    gemini_ok = test_gemini()
    db_ok = test_db()

    if gemini_ok and db_ok:
        print("\n✅ All systems normal.")
    else:
        print("\n❌ Errors detected. Please check the output above.")
