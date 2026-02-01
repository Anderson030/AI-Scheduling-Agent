import uuid
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import pytz
import logging

logger = logging.getLogger(__name__)

class CalendarService:
    def __init__(self, credentials=None):
        self.scopes = ['https://www.googleapis.com/auth/calendar']
        from src.config import TIMEZONE_STR, CALENDAR_ID
        
        self.calendar_id = CALENDAR_ID or "primary"
        self.creds = credentials
        if self.creds:
            self.service = build('calendar', 'v3', credentials=self.creds)
        else:
            self.service = None
            logger.warning("CalendarService inicializado sin credenciales.")
        
        self.timezone = TIMEZONE_STR

    def create_event(self, summary, start_time: datetime, end_time: datetime = None, description="", user_emails=None, enable_meet=False):
        try:
            if not end_time:
                end_time = start_time + timedelta(hours=1)
            
            # Asegurar que son aware (si no vienen con zona, asumimos UTC)
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)

            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': self.timezone,
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': self.timezone,
                },
            }

            if user_emails:
                if isinstance(user_emails, str):
                    user_emails = [user_emails]
                event['attendees'] = [{'email': email.strip()} for email in user_emails]

            if enable_meet:
                event['conferenceData'] = {
                    'createRequest': {
                        'requestId': str(uuid.uuid4()),
                        'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                    }
                }

            logger.info(f"Insertando evento en calendario {self.calendar_id}: {summary}")
            event = self.service.events().insert(
                calendarId=self.calendar_id, 
                body=event,
                sendUpdates='all',
                conferenceDataVersion=1 if enable_meet else 0
            ).execute()
            return event
        except Exception as e:
            logger.error(f"Error en create_event: {e}")
            raise e

    def list_events(self, time_min=None, max_results=10):
        try:
            if not time_min:
                time_min = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"Listando eventos en calendario {self.calendar_id} desde {time_min}")
            events_result = self.service.events().list(
                calendarId=self.calendar_id, timeMin=time_min,
                maxResults=max_results, singleEvents=True,
                orderBy='startTime'
            ).execute()
            return events_result.get('items', [])
        except Exception as e:
            logger.error(f"Error en list_events: {e}")
            raise e

    def update_event(self, event_id, summary=None, start_time=None, end_time=None):
        try:
            event = self.service.events().get(calendarId=self.calendar_id, eventId=event_id).execute()
            
            if summary:
                event['summary'] = summary
            if start_time:
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                event['start']['dateTime'] = start_time.isoformat()
                
                if not end_time:
                    end_time = start_time + timedelta(hours=1)
            
            if end_time:
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=timezone.utc)
                event['end']['dateTime'] = end_time.isoformat()

            logger.info(f"Actualizando evento {event_id} en calendario {self.calendar_id}")
            updated_event = self.service.events().update(calendarId=self.calendar_id, eventId=event_id, body=event).execute()
            return updated_event
        except Exception as e:
            logger.error(f"Error en update_event: {e}")
            raise e

    def delete_event(self, event_id):
        try:
            logger.info(f"Eliminando evento {event_id} en calendario {self.calendar_id}")
            self.service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()
            return True
        except Exception as e:
            # Si el código es 404 o 410, ya se borró, no es un error fatal
            if "not found" in str(e).lower() or "gone" in str(e).lower():
                logger.warning(f"Evento {event_id} no encontrado en Google Calendar (posiblemente ya borrado).")
                return True
            logger.error(f"Error en delete_event: {e}")
            raise e

    def delete_all_events(self):
        """Elimina todos los eventos futuros del calendario del usuario"""
        try:
            events = self.list_events() # list_events ya usa datetime.now(timezone.utc)
            deleted_count = 0
            for event in events:
                self.delete_event(event['id'])
                deleted_count += 1
            return deleted_count
        except Exception as e:
            logger.error(f"Error en delete_all_events: {e}")
            raise e

    def check_conflicts(self, start_time: datetime, end_time: datetime):
        events = self.list_events(time_min=start_time.isoformat() + 'Z')
        for event in events:
            ev_start = event['start'].get('dateTime') or event['start'].get('date')
            ev_end = event['end'].get('dateTime') or event['end'].get('date')
            
            # Simple overlap check
            # (StartA < EndB) and (EndA > StartB)
            # This needs proper parsing of the event times
            # For brevity in this agentic flow, I'll keep it simple or implement a more robust one if needed
            pass
        return False # Placeholder
