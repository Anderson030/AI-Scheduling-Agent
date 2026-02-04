from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import SessionLocal, Appointment
from src.config import TIMEZONE
from datetime import datetime, timedelta, timezone
import logging

logger = logging.getLogger(__name__)

class SchedulerService:
    def __init__(self, bot_instance):
        self.scheduler = AsyncIOScheduler(timezone=TIMEZONE)
        self.bot = bot_instance

    def start(self):
        self.scheduler.add_job(self.check_reminders, 'interval', minutes=5)
        self.scheduler.start()

    async def check_reminders(self):
        db = SessionLocal()
        # Usamos UTC para comparar con lo guardado en DB (naive UTC)
        now_utc = datetime.utcnow()
        
        # Consultar citas futuras (que no hayan pasado ya)
        appointments = db.query(Appointment).filter(
            Appointment.start_time > now_utc
        ).all()

        for appt in appointments:
            try:
                # Convertir naive UTC de DB a aware UTC para cálculos
                start_utc = appt.start_time.replace(tzinfo=timezone.utc)
                diff = start_utc - now_utc.replace(tzinfo=timezone.utc)
                
                # Convertir a zona horaria local para el mensaje
                from src.config import TIMEZONE
                start_local = start_utc.astimezone(TIMEZONE)
                now_local = datetime.now(TIMEZONE)
                
                time_str = start_local.strftime('%H:%M')
                
                # Determinar si es hoy o mañana localmente
                if start_local.date() == now_local.date():
                    day_str = "hoy"
                elif start_local.date() == (now_local + timedelta(days=1)).date():
                    day_str = "mañana"
                else:
                    day_str = f"el {start_local.strftime('%d/%m')}"

                message_template = f"Recordatorio: Tienes una cita '{appt.title}' {day_str} a las {time_str}. recuerda estar 10 minutos antes ¿Quieres que te envie el link del meet?"
                
                message = None
                field_to_mark = None
                
                # Lógica de ventanas no solapadas
                if diff <= timedelta(minutes=15):
                    if not appt.rem_15m_sent:
                        message = message_template
                        field_to_mark = "rem_15m_sent"
                elif diff <= timedelta(hours=1):
                    if not appt.rem_1h_sent:
                        message = message_template
                        field_to_mark = "rem_1h_sent"
                elif diff <= timedelta(hours=3):
                    if not appt.rem_3h_sent:
                        message = message_template
                        field_to_mark = "rem_3h_sent"
                elif diff <= timedelta(hours=24):
                    if not appt.rem_24h_sent:
                        message = message_template
                        field_to_mark = "rem_24h_sent"

                if message and field_to_mark:
                    await self.bot.send_message(chat_id=appt.telegram_id, text=message)
                    setattr(appt, field_to_mark, True)
                    # Marcar también los anteriores para no enviarlos después si por algo se saltan
                    if field_to_mark == "rem_3h_sent": appt.rem_24h_sent = True
                    if field_to_mark == "rem_1h_sent": 
                        appt.rem_24h_sent = True
                        appt.rem_3h_sent = True
                    if field_to_mark == "rem_15m_sent":
                        appt.rem_24h_sent = True
                        appt.rem_3h_sent = True
                        appt.rem_1h_sent = True
                        
                    db.commit()
                    logger.info(f"Recordatorio {field_to_mark} enviado para la cita {appt.id}")
                    
            except Exception as e:
                logger.error(f"Error procesando cita {appt.id} en scheduler: {e}")
                db.rollback()
        
        db.close()
