import logging
import json
import os
import traceback
from telegram import Update
from telegram.ext import ContextTypes

from src.ai import AIService, TOOLS
from src.auth_manager import AuthManager
from src.history_manager import HistoryManager
from src.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.ai = AIService()

    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "¡Hola! Soy tu asistente de citas personal. "
            "Para gestionar tus citas, primero necesito conectarme a tu Google Calendar.\n\n"
            "Usa /conectar para empezar."
        )

    async def conectar_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        from src.config import WEBHOOK_URL
        auth_url = f"{WEBHOOK_URL}/auth/url?telegram_id={user_id}"
        await update.message.reply_text(
            f"Haz clic aquí para autorizar el acceso:\n\n[Conectar con Google]({auth_url})",
            parse_mode="Markdown"
        )

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = str(update.effective_user.id)
            
            # 1. Verificar Autenticación
            if not AuthManager.is_user_authenticated(user_id):
                await update.message.reply_text("Primero debes conectar tu cuenta de Google. Usa /conectar.")
                return

            # 2. Obtener texto (Audio o Texto)
            text = update.message.text
            if update.message.voice or update.message.audio:
                await update.message.reply_text("Procesando tu audio...")
                audio_file = await context.bot.get_file(update.message.voice.file_id or update.message.audio.file_id)
                audio_path = f"downloads/{update.message.voice.file_unique_id}.ogg"
                os.makedirs("downloads", exist_ok=True)
                await audio_file.download_to_drive(audio_path)
                text = self.ai.transcribe_audio(audio_path)
                await update.message.reply_text(f"He escuchado: \"{text}\"")

            if not text: return

            # 3. Gestionar Historial y obtener respuesta de IA
            messages = HistoryManager.get_user_history(user_id)
            messages.append({"role": "user", "content": text})
            HistoryManager.save_message(user_id, "user", text)

            logger.info(f"Solicitando respuesta de IA para {user_id}...")
            response_msg = self.ai.get_agent_response(messages, TOOLS)
            
            # Guardar respuesta assistant (puede ser el texto o el objeto con tool_calls)
            HistoryManager.save_message(
                user_id, 
                "assistant", 
                response_msg.model_dump() if response_msg.tool_calls else response_msg.content
            )
            
            messages.append(response_msg.model_dump() if hasattr(response_msg, 'model_dump') else response_msg)

            # 4. Procesar Herramientas si es necesario
            reply_text = response_msg.content
            if response_msg.tool_calls:
                logger.info(f"IA solicitó {len(response_msg.tool_calls)} herramientas para {user_id}")
                calendar_service = AuthManager.get_calendar_service(user_id)
                
                for tool_call in response_msg.tool_calls:
                    function_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    result = await ToolExecutor.execute(function_name, args, user_id, calendar_service)
                    
                    HistoryManager.save_message(user_id, "tool", json.dumps(result), 
                                              tool_call_id=tool_call.id, name=function_name)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "name": function_name, "content": json.dumps(result)})

                logger.info(f"Solicitando respuesta final de IA tras herramientas para {user_id}...")
                final_response = self.ai.get_agent_response(messages, TOOLS)
                reply_text = final_response.content
                HistoryManager.save_message(user_id, "assistant", reply_text)

            logger.info(f"Enviando respuesta a {user_id}: {reply_text[:50] if reply_text else 'None'}...")
            await update.message.reply_text(reply_text or "No recibí respuesta de la IA.")
            
        except Exception as e:
            logger.error(f"Error en message_handler: {e}")
            logger.error(traceback.format_exc())
            await update.message.reply_text("Lo siento, tuve un problema interno. Inténtalo de nuevo.")

    def send_message(self, chat_id, text):
        # Implementado mediante inyección en main.py (context.bot.send_message)
        pass
