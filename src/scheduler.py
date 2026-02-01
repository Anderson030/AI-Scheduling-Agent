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
                
                message = None
                field_to_mark = None
                
                # Lógica de ventanas no solapadas
                # Priorizamos el más inminente que no haya sido enviado
                if diff <= timedelta(minutes=15):
                    if not appt.rem_15m_sent:
                        message = f"Recordatorio: Tienes una cita '{appt.title}' programada para en 15 minutos a las {appt.start_time.strftime('%H:%M')}."
                        field_to_mark = "rem_15m_sent"
                elif diff <= timedelta(hours=1):
                    if not appt.rem_1h_sent:
                        message = f"Recordatorio: Tienes una cita '{appt.title}' programada para en 1 hora a las {appt.start_time.strftime('%H:%M')}."
                        field_to_mark = "rem_1h_sent"
                elif diff <= timedelta(hours=3):
                    if not appt.rem_3h_sent:
                        message = f"Recordatorio: Tienes una cita '{appt.title}' programada para en 3 horas a las {appt.start_time.strftime('%H:%M')}."
                        field_to_mark = "rem_3h_sent"
                elif diff <= timedelta(hours=24):
                    if not appt.rem_24h_sent:
                        # Solo enviamos el de 24h si falta más de 3h para no ser redundante
                        # (Aunque el elif ya maneja la exclusión, esto es doble seguridad)
                        message = f"Recordatorio: Tienes una cita '{appt.title}' programada para mañana a las {appt.start_time.strftime('%H:%M')}."
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
