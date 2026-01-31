import logging
import json
from telegram import Update
from telegram.ext import ContextTypes
from src.ai import AIService, TOOLS
from src.calendar_api import CalendarService
from src.database import SessionLocal, Appointment, UserAuth
from datetime import datetime, timedelta
import os
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, token):
        self.token = token
        self.ai = AIService()
        self.user_sessions = {} # {telegram_id: [messages]}

    def get_calendar_service(self, user_id):
        db = SessionLocal()
        user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == user_id).first()
        db.close()
        
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
        return CalendarService(credentials=creds)

    async def start_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "¡Hola! Soy tu asistente de citas personal. "
            "Para poder gestionar tus citas, primero necesito conectarme a **tu** Google Calendar.\n\n"
            "Usa el comando /conectar para empezar."
        )

    async def conectar_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        from src.config import WEBHOOK_URL
        auth_url = f"{WEBHOOK_URL}/auth/url?telegram_id={user_id}"
        await update.message.reply_text(
            f"Por favor, haz clic en el siguiente enlace para autorizar el acceso a tu calendario:\n\n"
            f"[Conectar con Google]({auth_url})",
            parse_mode="Markdown"
        )

    async def message_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = str(update.effective_user.id)
            
            # Verificar si el usuario tiene permiso (Auth)
            db = SessionLocal()
            user_auth = db.query(UserAuth).filter(UserAuth.telegram_id == user_id).first()
            db.close()
            
            if not user_auth:
                await update.message.reply_text("Primero debes conectar tu cuenta de Google. Usa /conectar para obtener el link.")
                return

            text = update.message.text
            logger.info(f"Mensaje recibido de {user_id}: {text}")
            
            # Si es audio, transcribir
            if update.message.voice or update.message.audio:
                logger.info(f"Procesando audio de {user_id}")
                await update.message.reply_text("Procesando tu audio...")
                audio_file = await context.bot.get_file(update.message.voice.file_id or update.message.audio.file_id)
                audio_path = f"downloads/{update.message.voice.file_unique_id}.ogg"
                os.makedirs("downloads", exist_ok=True)
                await audio_file.download_to_drive(audio_path)
                text = self.ai.transcribe_audio(audio_path)
                logger.info(f"Trascripción para {user_id}: {text}")
                await update.message.reply_text(f"He escuchado: \"{text}\"")

            if not text:
                logger.warning(f"Mensaje vacío recibido de {user_id}")
                return

            # Obtener historial
            messages = self.user_sessions.get(user_id, [])
            messages.append({"role": "user", "content": text})

            # Obtener respuesta de la IA
            logger.info(f"Solicitando respuesta de IA para {user_id}...")
            response_msg = self.ai.get_agent_response(messages, TOOLS)
            logger.info(f"IA respondió para {user_id}")
            
            # Añadir la respuesta del asistente (que puede contener tool_calls) al historial
            # Es CRÍTICO que el mensaje del assistant esté antes de los resultados de las herramientas
            messages.append(response_msg)

            # Procesar Tool Calls
            if response_msg.tool_calls:
                logger.info(f"IA solicitó {len(response_msg.tool_calls)} herramientas para {user_id}")
                for tool_call in response_msg.tool_calls:
                    function_name = tool_call.function.name
                    args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"Ejecutando {function_name} para {user_id} con args: {args}")
                    
                    # Obtener servicio de calendario del usuario
                    calendar_service = self.get_calendar_service(user_id)
                    if not calendar_service:
                        result = {"status": "error", "message": "No se encontró conexión con Google Calendar. Usa /conectar."}
                    else:
                        result = await self.execute_tool(function_name, args, user_id, calendar_service)
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": json.dumps(result)
                    })
                
                # Segunda llamada a la IA con el resultado de la herramienta
                logger.info(f"Solicitando respuesta final de IA tras herramientas para {user_id}...")
                final_response = self.ai.get_agent_response(messages, TOOLS)
                reply_text = final_response.content
                messages.append({"role": "assistant", "content": reply_text})
            else:
                reply_text = response_msg.content
                # El mensaje ya se añadió arriba (línea 61 aproximadamente en el archivo original)
                # No es necesario añadirlo de nuevo si no hubo tool calls

            # Limitar historial de forma segura (manteniendo pares assistant-tool si es necesario)
            # Para simplificar, limitamos a 15 y nos aseguramos de no empezar con una herramienta
            if len(messages) > 15:
                messages = messages[-15:]
                # Si el primer mensaje es de rol 'tool', lo quitamos para evitar errores de OpenAI
                while messages and messages[0].get('role') == 'tool':
                    messages.pop(0)

            self.user_sessions[user_id] = messages
            
            logger.info(f"Enviando respuesta a {user_id}: {reply_text[:50]}...")
            await update.message.reply_text(reply_text)
        except Exception as e:
            logger.error(f"Error crítico en message_handler: {e}", exc_info=True)
            await update.message.reply_text("Lo siento, tuve un problema interno al procesar tu mensaje.")

    async def execute_tool(self, name, args, telegram_id, calendar_service):
        try:
            if name == "create_appointment":
                start_dt = datetime.fromisoformat(args['start_time'].replace('Z', '+00:00'))
                end_dt = None
                if 'end_time' in args:
                    end_dt = datetime.fromisoformat(args['end_time'].replace('Z', '+00:00'))
                
                # Extraer el correo del usuario si fue proporcionado por la IA
                user_email = args.get('user_email')
                
                event = calendar_service.create_event(args['summary'], start_dt, end_dt, user_email=user_email)
                
                # Guardar en DB para recordatorios (asociando el correo si está disponible)
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
                
                return {"status": "success", "event_id": event['id'], "user_email": user_email}

            elif name == "list_appointments":
                events = calendar_service.list_events(args.get('time_min'))
                # Simplificar para la IA
                simplified = [{"id": e['id'], "summary": e['summary'], "start": e['start']} for e in events]
                return simplified

            elif name == "update_appointment":
                start_dt = None
                if 'start_time' in args:
                    start_dt = datetime.fromisoformat(args['start_time'].replace('Z', '+00:00'))
                
                event = calendar_service.update_event(args['event_id'], summary=args.get('summary'), start_time=start_dt)
                
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
                calendar_service.delete_event(args['event_id'])
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
