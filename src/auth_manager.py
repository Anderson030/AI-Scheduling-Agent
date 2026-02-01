import logging
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from src.database import SessionLocal, UserAuth
from src.calendar_api import CalendarService

logger = logging.getLogger(__name__)

class AuthManager:
    @staticmethod
    def get_calendar_service(user_id: str):
        """Obtiene y refresca el servicio de calendario para un usuario específico"""
        db = SessionLocal()
        try:
            user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == user_id).first()
            
            if not user_auth:
                return None
                
            creds = Credentials(
                token=user_auth.access_token,
                refresh_token=user_auth.refresh_token,
                token_uri=user_auth.token_uri,
                client_id=user_auth.client_id,
                client_secret=user_auth.client_secret,
                scopes=user_auth.scopes.split(",")
            )
            
            # Refrescar token si ha expirado
            if creds.expired and creds.refresh_token:
                try:
                    logger.info(f"Refrescando token para usuario {user_id}")
                    creds.refresh(Request())
                    user_auth.access_token = creds.token
                    user_auth.expires_at = creds.expiry.replace(tzinfo=None) if creds.expiry else None
                    db.commit()
                except Exception as e:
                    logger.error(f"Error al refrescar token de Google: {e}")
            
            return CalendarService(credentials=creds)
        finally:
            db.close()

    @staticmethod
    def is_user_authenticated(user_id: str) -> bool:
        """Verifica si el usuario ya vinculó su cuenta de Google"""
        db = SessionLocal()
        try:
            user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == user_id).first()
            return user_auth is not None
        finally:
            db.close()
