from apscheduler.schedulers.asyncio import AsyncIOScheduler
from src.database import SessionLocal, Appointment
from src.config import TIMEZONE
from datetime import datetime, timedelta
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
        now = datetime.now(TIMEZONE)
        
        # Definir intervalos y sus nombres de columna
        reminders = [
            (timedelta(hours=24), "rem_24h_sent", "mañana"),
            (timedelta(hours=3), "rem_3h_sent", "en 3 horas"),
            (timedelta(hours=1), "rem_1h_sent", "en 1 hora"),
            (timedelta(minutes=15), "rem_15m_sent", "en 15 minutos")
        ]

        for delta, field, time_text in reminders:
            target_time = now + delta
            # Citas que ocurren pronto y no han recibido este recordatorio específico
            # Usamos un margen pequeño para evitar enviar recordatorios tarde si el scheduler se atrasa
            appointments = db.query(Appointment).filter(
                Appointment.start_time <= target_time,
                Appointment.start_time > now,
                getattr(Appointment, field) == False
            ).all()

            for appt in appointments:
                try:
                    message = f"Recordatorio: Tienes una cita '{appt.title}' programada para {time_text} a las {appt.start_time.strftime('%H:%M')}."
                    await self.bot.send_message(chat_id=appt.telegram_id, text=message)
                    setattr(appt, field, True)
                    db.commit()
                    logger.info(f"Recordatorio {field} enviado para la cita {appt.id}")
                except Exception as e:
                    logger.error(f"Error enviando recordatorio {field}: {e}")
        
        db.close()
