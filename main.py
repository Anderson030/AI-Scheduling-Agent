import logging
import os
import uvicorn
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from src.config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL
from src.bot import TelegramBot
from src.database import init_db
from src.scheduler import SchedulerService
from src.auth_routes import router as auth_router

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI App
app = FastAPI(title="Asistente de Citas AI")
app.include_router(auth_router)

# Inicialización de DB y Bot
init_db()
bot_logic = TelegramBot(TELEGRAM_BOT_TOKEN)
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
scheduler = SchedulerService(application.bot)

@app.on_event("startup")
async def startup_event():
    # Registrar manejadores del bot
    application.add_handler(CommandHandler("start", bot_logic.start_handler))
    application.add_handler(CommandHandler("conectar", bot_logic.conectar_handler))
    application.add_handler(CommandHandler("reset", bot_logic.reset_handler))
    application.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.AUDIO, bot_logic.message_handler))
    
    await application.initialize()
    
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/webhook")
        logger.info(f"Modo WEBHOOK: Configurado en {WEBHOOK_URL}/webhook")
        await application.start()
    else:
        logger.info("Modo POLLING: Iniciando...")
        await application.start()
        asyncio.create_task(application.updater.start_polling())
    
    scheduler.start()
    logger.info("Sistema de gestión de citas iniciado correctamente.")

@app.on_event("shutdown")
async def shutdown_event():
    await application.stop()
    await application.shutdown()

@app.post("/webhook")
async def webhook_handler(request: Request):
    """Maneja las actualizaciones de Telegram"""
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"status": "ok"}

@app.get("/")
def health_check():
    return {"status": "online", "message": "Asistente de Citas AI funcionando"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
