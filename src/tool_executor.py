import logging
import json
from datetime import datetime, timedelta, timezone
from src.database import SessionLocal, Appointment
from src.calendar_api import CalendarService

logger = logging.getLogger(__name__)

class ToolExecutor:
    @staticmethod
    async def execute(name, args, telegram_id, calendar_service: CalendarService):
        """Ejecuta la lógica de una herramienta específica recibida de la IA"""
        try:
            if name == "create_appointment":
                return await ToolExecutor._create_appointment(args, telegram_id, calendar_service)
            elif name == "list_appointments":
                return ToolExecutor._list_appointments(args, calendar_service)
            elif name == "update_appointment":
                return await ToolExecutor._update_appointment(args, calendar_service)
            elif name == "delete_appointment":
                return await ToolExecutor._delete_appointment(args, calendar_service)
            
            return {"status": "error", "message": f"Herramienta '{name}' no reconocida."}
        except Exception as e:
            logger.error(f"Error ejecutando ferramenta {name}: {e}")
            return {"status": "error", "message": str(e)}

    @staticmethod
    async def _create_appointment(args, telegram_id, calendar_service):
        start_dt = datetime.fromisoformat(args['start_time'].replace('Z', '+00:00'))
        if start_dt.tzinfo is None:
            # Si viene sin zona horaria, asumimos UTC por el formato ISO de la IA
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        else:
            start_dt = start_dt.astimezone(timezone.utc)

        end_dt = None
        if 'end_time' in args:
            end_dt = datetime.fromisoformat(args['end_time'].replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            else:
                end_dt = end_dt.astimezone(timezone.utc)
        
        user_emails = args.get('user_emails', [])
        # Soporte para el campo antiguo por si acaso la IA se confunde al principio
        if not user_emails and 'user_email' in args:
            user_emails = [args['user_email']]
            
        enable_meet = args.get('enable_meet', False)
        
        event = calendar_service.create_event(
            args['summary'], 
            start_dt, 
            end_dt, 
            user_emails=user_emails, 
            enable_meet=enable_meet
        )
        
        # Guardar en DB para seguimiento
        db = SessionLocal()
        try:
            new_appt = Appointment(
                telegram_id=telegram_id,
                event_id=event['id'],
                title=args['summary'],
                start_time=start_dt.replace(tzinfo=None), # Guardamos como naive UTC
                end_time=(end_dt or (start_dt + timedelta(hours=1))).replace(tzinfo=None) # Guardamos como naive UTC
            )
            db.add(new_appt)
            db.commit()
        finally:
            db.close()
            
        meet_link = event.get('hangoutLink')
        return {
            "status": "success", 
            "event_id": event['id'], 
            "user_emails": user_emails,
            "meet_link": meet_link
        }

    @staticmethod
    def _list_appointments(args, calendar_service):
        events = calendar_service.list_events(args.get('time_min'))
        return [{"id": e['id'], "summary": e['summary'], "start": e['start']} for e in events]

    @staticmethod
    async def _update_appointment(args, calendar_service):
        start_dt = None
        if 'start_time' in args:
            start_dt = datetime.fromisoformat(args['start_time'].replace('Z', '+00:00'))
        
        event = calendar_service.update_event(args['event_id'], summary=args.get('summary'), start_time=start_dt)
        
        # Actualizar DB
        db = SessionLocal()
        try:
            appt = db.query(Appointment).filter(Appointment.event_id == args['event_id']).first()
            if appt:
                if 'summary' in args: appt.title = args['summary']
                if start_dt: 
                    # Asegurar UTC antes de guardar
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                    else:
                        start_dt = start_dt.astimezone(timezone.utc)
                    appt.start_time = start_dt.replace(tzinfo=None)
                db.commit()
        finally:
            db.close()
            
        return {"status": "success", "event_id": event['id']}

    @staticmethod
    async def _delete_appointment(args, calendar_service):
        calendar_service.delete_event(args['event_id'])
        db = SessionLocal()
        try:
            db.query(Appointment).filter(Appointment.event_id == args['event_id']).delete()
            db.commit()
        finally:
            db.close()
        return {"status": "success"}
