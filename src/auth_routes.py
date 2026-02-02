import logging
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import google_auth_oauthlib.flow
from datetime import datetime, timedelta
import requests
from src.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, WEBHOOK_URL
from src.database import SessionLocal, UserAuth

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/auth/url")
async def get_auth_url(telegram_id: str):
    """Genera la URL de autorización para un usuario de Telegram específico"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return {"error": "GOOGLE_CLIENT_ID o GOOGLE_CLIENT_SECRET no están configurados"}
        
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=[
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/gmail.send'
        ]
    )
    flow.redirect_uri = f"{WEBHOOK_URL}/auth/callback"
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true',
        state=telegram_id
    )
    return RedirectResponse(authorization_url)

@router.get("/auth/callback")
async def auth_callback(request: Request):
    """Recibe el código de Google, obtiene los tokens y los guarda para el usuario"""
    try:
        code = request.query_params.get("code")
        telegram_id = request.query_params.get("state")
        
        redirect_uri = f"{WEBHOOK_URL}/auth/callback"
        
        if not code or not telegram_id:
            return {"status": "error", "message": "Faltan parámetros."}

        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        response = requests.post(token_url, data=payload)
        tokens = response.json()

        if response.status_code != 200:
            logger.error(f"Error en intercambio de tokens: {tokens}")
            return {"status": "error", "message": "Google rechazó las credenciales."}

        access_token = tokens.get('access_token')
        refresh_token = tokens.get('refresh_token')
        expires_in = tokens.get('expires_in', 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        db = SessionLocal()
        try:
            user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == telegram_id).first()
            if not user_auth:
                user_auth = UserAuth(telegram_id=telegram_id)
                db.add(user_auth)
            
            user_auth.access_token = access_token
            if refresh_token:
                user_auth.refresh_token = refresh_token
            
            user_auth.token_uri = token_url
            user_auth.client_id = GOOGLE_CLIENT_ID
            user_auth.client_secret = GOOGLE_CLIENT_SECRET
            user_auth.scopes = tokens.get('scope', 'https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.send')
            user_auth.expires_at = expires_at

            db.commit()
            logger.info(f"Tokens guardados exitosamente para usuario {telegram_id}")
        finally:
            db.close()

        return {"status": "success", "message": "¡Tu calendario ha sido conectado con éxito!"}
    except Exception as e:
        logger.error(f"Error crítico en auth_callback: {e}")
        return {"status": "error", "message": str(e)}
