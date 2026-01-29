import logging
import uvicorn
from fastapi import FastAPI, Request, BackgroundTasks
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from src.config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL
from src.bot import TelegramBot
from src.database import init_db
from src.scheduler import SchedulerService

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

@app.get("/")
def health_check():
    return {"status": "online", "message": "Asistente de Citas AI funcionando"}

if __name__ == "__main__":
    # Si se corre localmente sin webhook, se puede usar polling para pruebas rápidas
    # Pero los requerimientos pedían FastApi + Webhook
    uvicorn.run(app, host="0.0.0.0", port=8000)
