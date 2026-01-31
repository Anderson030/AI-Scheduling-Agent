import logging
import os
import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from src.config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL as RAW_WEBHOOK_URL, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from src.bot import TelegramBot
from src.database import init_db, SessionLocal, UserAuth
from src.scheduler import SchedulerService
import google_auth_oauthlib.flow
from fastapi.responses import RedirectResponse
from datetime import datetime

# Normalizar funciones de limpieza
def clean_env_var(val):
    if not val: return None
    import re
    # Eliminar cualquier cosa que no sea un carácter alfanumérico o símbolos válidos en keys
    # (Espacios, tabulaciones, comillas accidentales, etc.)
    return re.sub(r'[\s\t\n\r"\' ]', '', val).strip()

# Cargar y limpiar variables
WEBHOOK_URL = RAW_WEBHOOK_URL.rstrip('/') if RAW_WEBHOOK_URL else None
GOOGLE_CLIENT_ID = clean_env_var(os.getenv("GOOGLE_CLIENT_ID"))
GOOGLE_CLIENT_SECRET = clean_env_var(os.getenv("GOOGLE_CLIENT_SECRET"))

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Diagnóstico inicial
logger.info(f"Config: WEBHOOK_URL={WEBHOOK_URL}")
if GOOGLE_CLIENT_ID:
    logger.info(f"Config: GOOGLE_CLIENT_ID detectado (Empieza por: {GOOGLE_CLIENT_ID[:10]}...)")
else:
    logger.warning("Config: GOOGLE_CLIENT_ID NO DETECTADO")

# FastAPI
app = FastAPI()

# Inicializar Base de Datos
init_db()

# Inicializar Bot y Scheduler
bot_logic = TelegramBot(TELEGRAM_BOT_TOKEN)
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# Recordatorios
scheduler = SchedulerService(application.bot)

@app.on_event("startup")
async def startup_event():
    # Registrar manejadores del bot
    application.add_handler(CommandHandler("start", bot_logic.start_handler))
    application.add_handler(CommandHandler("conectar", bot_logic.conectar_handler))
    application.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.AUDIO, bot_logic.message_handler))
    
    await application.initialize()
    
    if WEBHOOK_URL:
        # Modo Webhook (Recomendado para Producción)
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"Modo WEBHOOK: Configurado en {WEBHOOK_URL}/webhook")
        await application.start()
    else:
        # Modo Polling (Recomendado para Pruebas Locales)
        logger.info("Modo POLLING: Iniciando... (No necesitas ngrok ni URL pública)")
        await application.start()
        # En Polling, necesitamos iniciar el actualizador manualmente en el ciclo de FastAPI
        import asyncio
        asyncio.create_task(application.updater.start_polling())
    
    # Iniciar Scheduler
    scheduler.start()
    logger.info("Sistema de gestión de citas iniciado correctamente.")

@app.on_event("shutdown")
async def shutdown_event():
    await application.stop()
    await application.shutdown()

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Maneja las actualizaciones enviadas por Telegram vía Webhook"""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

@app.get("/auth/url")
async def get_auth_url(telegram_id: str):
    """Genera la URL de autorización para un usuario de Telegram específico"""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return {"error": "GOOGLE_CLIENT_ID o GOOGLE_CLIENT_SECRET no están configurados en Railway"}
        
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        {
            "web": {
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    flow.redirect_uri = f"{WEBHOOK_URL}/auth/callback"
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',  # Forzar a que Google entregue un Refresh Token siempre
        include_granted_scopes='true',
        state=telegram_id
    )
    return RedirectResponse(authorization_url)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    """Recibe el código de Google, obtiene los tokens y los guarda para el usuario"""
    try:
        import requests
        code = request.query_params.get("code")
        telegram_id = request.query_params.get("state")
        
        redirect_uri = f"{WEBHOOK_URL}/auth/callback"
        logger.info(f"Callback recibido. TelegramID: {telegram_id}")
        logger.info(f"Redirect URI configurada: {redirect_uri}")
        
        if not code or not telegram_id:
            return {"status": "error", "message": "Faltan parámetros."}

        # Intercambio manual para ver el error real de Google
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            'code': code,
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        
        logger.info(f"Enviando petición a Google Token URL con ClientID: {GOOGLE_CLIENT_ID[:15]}...")
        response = requests.post(token_url, data=payload)
        tokens = response.json()

        if response.status_code != 200:
            logger.error(f"Error en intercambio de tokens: {tokens}")
            return {
                "status": "error", 
                "message": f"Google rechazó las credenciales (invalid_client). Detalle: {tokens.get('error_description', tokens.get('error'))}",
                "debug_info": {
                    "sent_redirect_uri": redirect_uri,
                    "google_response": tokens
                }
            }

        access_token = tokens.get('access_token')
        refresh_token = tokens.get('refresh_token')
        expires_in = tokens.get('expires_in', 3600)
        
        # Calcular fecha expiración
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Guardar en DB
        db = SessionLocal()
        try:
            user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == telegram_id).first()
            if not user_auth:
                user_auth = UserAuth(telegram_id=telegram_id)
                db.add(user_auth)
            
            user_auth.access_token = access_token
            if refresh_token: # Solo viene la primera vez o si forzamos consent
                user_auth.refresh_token = refresh_token
            
            user_auth.token_uri = token_url
            user_auth.client_id = GOOGLE_CLIENT_ID
            user_auth.client_secret = GOOGLE_CLIENT_SECRET
            user_auth.scopes = tokens.get('scope', 'https://www.googleapis.com/auth/calendar')
            user_auth.expires_at = expires_at

            db.commit()
            logger.info(f"Tokens guardados exitosamente para usuario {telegram_id}")
        except Exception as db_e:
            db.rollback()
            logger.error(f"Error DB: {db_e}")
            raise db_e
        finally:
            db.close()

        return {"status": "success", "message": "¡Tu calendario ha sido conectado con éxito! Ya puedes volver a Telegram."}
    except Exception as e:
        logger.error(f"Error crítico en auth_callback: {e}", exc_info=True)
        return {"status": "error", "message": f"Ocurrió un error interno: {str(e)}"}

@app.get("/")
def health_check():
    return {"status": "online", "message": "Asistente de Citas AI funcionando"}

if __name__ == "__main__":
    # Si se corre localmente sin webhook, se puede usar polling para pruebas rápidas
    # Pero los requerimientos pedían FastApi + Webhook
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
