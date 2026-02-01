import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from src.database import SessionLocal, UserAuth
from src.calendar_api import CalendarService
from src.gmail_api import GmailService

logger = logging.getLogger(__name__)

class AuthManager:
    @staticmethod
    def _get_credentials(user_id: str):
        """Método interno para obtener y refrescar credenciales"""
        db = SessionLocal()
        try:
            user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == user_id).first()
            if not user_auth:
                return None, None

            creds = Credentials(
                token=user_auth.access_token,
                refresh_token=user_auth.refresh_token,
                token_uri=user_auth.token_uri,
                client_id=user_auth.client_id,
                client_secret=user_auth.client_secret,
                scopes=user_auth.scopes.replace(",", " ").split()
            )

            if creds.expired and creds.refresh_token:
                try:
                    logger.info(f"Refrescando token para usuario {user_id}")
                    creds.refresh(Request())
                    user_auth.access_token = creds.token
                    user_auth.expires_at = creds.expiry.replace(tzinfo=None) if creds.expiry else None
                    db.commit()
                except Exception as e:
                    logger.error(f"Error al refrescar token de Google: {e}")
            
            return creds, db
        except Exception as e:
            db.close()
            raise e

    @staticmethod
    def get_calendar_service(user_id: str):
        """Obtiene el servicio de calendario"""
        creds, db = AuthManager._get_credentials(user_id)
        if db: db.close()
        return CalendarService(credentials=creds) if creds else None

    @staticmethod
    def get_gmail_service(user_id: str):
        """Obtiene el servicio de Gmail"""
        creds, db = AuthManager._get_credentials(user_id)
        if db: db.close()
        return GmailService(credentials=creds) if creds else None

    @staticmethod
    def is_user_authenticated(user_id: str) -> bool:
        """Verifica si el usuario ya vinculó su cuenta de Google"""
        db = SessionLocal()
        try:
            user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == user_id).first()
            return user_auth is not None
        finally:
            db.close()
