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

# Normalizar variables (quitar espacios o slashes accidentales)
WEBHOOK_URL = RAW_WEBHOOK_URL.rstrip('/') if RAW_WEBHOOK_URL else None
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID").strip() if os.getenv("GOOGLE_CLIENT_ID") else None
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET").strip() if os.getenv("GOOGLE_CLIENT_SECRET") else None

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        code = request.query_params.get("code")
        telegram_id = request.query_params.get("state")
        
        if not code or not telegram_id:
            logger.error(f"Callback inválido: code={code}, state={telegram_id}")
            return {"status": "error", "message": "Faltan parámetros en el callback."}

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
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Guardar en DB
        db = SessionLocal()
        try:
            user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == telegram_id).first()
            if not user_auth:
                user_auth = UserAuth(telegram_id=telegram_id)
                db.add(user_auth)
            
            user_auth.access_token = creds.token
            user_auth.refresh_token = creds.refresh_token
            user_auth.token_uri = creds.token_uri
            user_auth.client_id = creds.client_id
            user_auth.client_secret = creds.client_secret
            user_auth.scopes = ",".join(creds.scopes)
            user_auth.expires_at = creds.expiry

            db.commit()
            logger.info(f"Tokens guardados exitosamente para usuario {telegram_id}")
        except Exception as db_e:
            db.rollback()
            logger.error(f"Error al guardar en base de datos: {db_e}")
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
