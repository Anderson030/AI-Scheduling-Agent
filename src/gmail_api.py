import logging
import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

class GmailService:
    def __init__(self, credentials=None):
        if not credentials:
            logger.error("GmailService inicializado sin credenciales.")
            raise Exception("Credenciales requeridas para GmailService")
        
        self.service = build('gmail', 'v1', credentials=credentials)

    def send_email(self, to, subject, body):
        """Envía un correo electrónico usando Gmail API"""
        try:
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            # Codificar en base64url para Google
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            logger.info(f"Enviando correo Gmail a {to} con asunto: {subject}")
            sent_message = self.service.users().messages().send(
                userId="me", 
                body={'raw': raw}
            ).execute()
            
            return sent_message
        except Exception as e:
            logger.error(f"Error en GmailService.send_email: {e}")
            raise e
