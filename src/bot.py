import logging
import json
from telegram import Update
from telegram.ext import ContextTypes
from src.ai import AIService, TOOLS
from src.calendar_api import CalendarService
from src.database import SessionLocal, Appointment
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.ai = AIService()
        self.calendar = CalendarService()
        self.user_sessions = {} # {telegram_id: [messages]}

    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "¡Hola! Soy tu asistente de citas. Puedo ayudarte a agendar, reprogramar o cancelar tus citas. "
            "Cuéntame, ¿qué necesitas hacer hoy? (Puedes escribirme o enviarme un audio)"
        )

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        text = update.message.text
        
        # Si es audio, transcribir
        if update.message.voice or update.message.audio:
            await update.message.reply_text("Procesando tu audio...")
            audio_file = await context.bot.get_file(update.message.voice.file_id or update.message.audio.file_id)
            audio_path = f"downloads/{update.message.voice.file_unique_id}.ogg"
            os.makedirs("downloads", exist_ok=True)
            await audio_file.download_to_drive(audio_path)
            text = self.ai.transcribe_audio(audio_path)
            await update.message.reply_text(f"He escuchado: \"{text}\"")

        if not text:
            return

        # Obtener historial
        messages = self.user_sessions.get(user_id, [])
        messages.append({"role": "user", "content": text})

        # Obtener respuesta de la IA
        response_msg = self.ai.get_agent_response(messages, TOOLS)
        
        # Procesar Tool Calls
        if response_msg.tool_calls:
            for tool_call in response_msg.tool_calls:
                function_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                result = await self.execute_tool(function_name, args, user_id)
                messages.append(response_msg)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": json.dumps(result)
                })
            
            # Segunda llamada a la IA con el resultado de la herramienta
            final_response = self.ai.get_agent_response(messages, TOOLS)
            reply_text = final_response.content
            messages.append({"role": "assistant", "content": reply_text})
        else:
            reply_text = response_msg.content
            messages.append({"role": "assistant", "content": reply_text})

        # Limitar historial
        self.user_sessions[user_id] = messages[-10:]
        
        await update.message.reply_text(reply_text)

    async def execute_tool(self, name, args, telegram_id):
        try:
            if name == "create_appointment":
                start_dt = datetime.fromisoformat(args['start_time'].replace('Z', '+00:00'))
                end_dt = None
                if 'end_time' in args:
                    end_dt = datetime.fromisoformat(args['end_time'].replace('Z', '+00:00'))
                
                event = self.calendar.create_event(args['summary'], start_dt, end_dt)
                
                # Guardar en DB para recordatorios
                db = SessionLocal()
                new_appt = Appointment(
                    telegram_id=telegram_id,
                    event_id=event['id'],
                    title=args['summary'],
                    start_time=start_dt,
                    end_time=end_dt or (start_dt + timedelta(hours=1))
                )
                db.add(new_appt)
                db.commit()
                db.close()
                
                return {"status": "success", "event_id": event['id']}

            elif name == "list_appointments":
                events = self.calendar.list_events(args.get('time_min'))
                # Simplificar para la IA
                simplified = [{"id": e['id'], "summary": e['summary'], "start": e['start']} for e in events]
                return simplified

            elif name == "update_appointment":
                start_dt = None
                if 'start_time' in args:
                    start_dt = datetime.fromisoformat(args['start_time'].replace('Z', '+00:00'))
                
                event = self.calendar.update_event(args['event_id'], summary=args.get('summary'), start_time=start_dt)
                
                # Actualizar DB
                db = SessionLocal()
                appt = db.query(Appointment).filter(Appointment.event_id == args['event_id']).first()
                if appt:
                    if 'summary' in args: appt.title = args['summary']
                    if start_dt: appt.start_time = start_dt
                    db.commit()
                db.close()
                
                return {"status": "success", "event_id": event['id']}

            elif name == "delete_appointment":
                self.calendar.delete_event(args['event_id'])
                db = SessionLocal()
                db.query(Appointment).filter(Appointment.event_id == args['event_id']).delete()
                db.commit()
                db.close()
                return {"status": "success"}

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return {"status": "error", "message": str(e)}

    def send_message(self, chat_id, text):
        # Esta función será llamada por el Scheduler
        # Requiere acceso al objeto bot de python-telegram-bot
        # Se implementará en main.py al inicializar la aplicación
        pass
