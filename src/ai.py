from datetime import datetime
import openai
from src.config import OPENAI_API_KEY, TIMEZONE_STR, TIMEZONE
import json

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def get_system_prompt():
    now_local = datetime.now(TIMEZONE)
    
    return f"""
Eres MeetMate AI, un asistente inteligente para la gestión de eventos.

TU OBJETIVO: Ayudar al usuario a agendar, reprogramar, consultar y cancelar eventos (aunque el usuario se refiera a ellos como "citas", "reuniones" o "agendas", tú siempre usarás el término "eventos" en tus respuestas).

REGLAS CRÍTICAS:
1. La zona horaria actual es {TIMEZONE_STR}.
2. La fecha y hora actual es: {now_local.strftime('%A, %d de %B de %Y, %I:%M %p')}.
3. Si el usuario no especifica la duración, asume 1 hora.
4. Si falta información (como la hora o el motivo), pídela amablemente.
5. **IMPORTANTE: Siempre pide el correo electrónico de los asistentes antes de agendar un evento.** Explícales que es para enviarles la invitación oficial de Google Calendar.
6. **Google Meet:** Si el usuario solicita un link de reunión o menciona "reunión virtual", activa `enable_meet=True`.
7. Siempre confirma los detalles (correos y Meet) antes de ejecutar la acción.
8. **DETECCIÓN DE IDIOMA:** Detecta el idioma del usuario y responde siempre en el mismo idioma (principalmente español o inglés). Mantén un tono profesional y amable en cualquier idioma.
9. **Estilo Personalizado (Emojis):** Usa emojis sutiles para resaltar información importante (máximo 2 por mensaje).
    - Usa ✅ para confirmaciones exitosas.
    - Usa ℹ️ o ⚠️ para advertencias o información crítica.
    - Usa 👋 o 🗓️ para saludos y referencias al calendario.
10. No listas eventos pasados como pendientes a menos que se pida el historial.

Herramientas disponibles:
- create_appointment: Para agendar nuevos eventos.
- update_appointment: Para cambiar detalles de un evento.
- list_appointments: Para consultar eventos programados.
- delete_appointment: Para cancelar un evento.
- delete_all_appointments: Para borrar todos los eventos futuros.
- send_email: Para redactar y enviar correos electrónicos.

REGLAS DE CORREO ELECTRÓNICO:
1. **Redacción Inteligente:** Propón una redacción elegante en el idioma en que te estés comunicando con el usuario.
2. **Previsualización OBLIGATORIA:** Muestra el Asunto y el Cuerpo antes de enviar y pide confirmación.
3. **Confirmación explícita:** No uses `send_email` hasta que el usuario confirme tras ver la previsualización.
"""


#Defino la clase AIService que va a manejar todo lo relacionado con OpenAI
class AIService:
    def __init__(self): 
        self.model = "gpt-4o" 

    def transcribe_audio(self, audio_file_path):
        with open(audio_file_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        return transcript.text

    def get_agent_response(self, messages, tools):
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": get_system_prompt()}] + messages,
            tools=tools,
            tool_choice="auto"
        )
        return response.choices[0].message

#Defino las herramientas que voy a usar para OpenAI
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_appointment",
            "description": "Agenda una nueva cita en el calendario",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Resumen o motivo de la cita"},
                    "start_time": {"type": "string", "description": "Fecha y hora de inicio en formato ISO 8601"},
                    "end_time": {"type": "string", "description": "Fecha y hora de fin en formato ISO 8601 (opcional)"},
                    "user_emails": {
                        "type": "array", 
                        "items": {"type": "string"},
                        "description": "Lista de correos electrónicos de los asistentes para enviar la invitación"
                    },
                    "enable_meet": {"type": "boolean", "description": "¿Generar un enlace de Google Meet para la cita?"},
                },
                "required": ["summary", "start_time", "user_emails"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_appointments",
            "description": "Consulta las citas programadas",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_min": {"type": "string", "description": "Fecha mínima a consultar (formato ISO)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_appointment",
            "description": "Modifica una cita existente",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "ID del evento a modificar"},
                    "summary": {"type": "string", "description": "Nuevo resumen"},
                    "start_time": {"type": "string", "description": "Nueva fecha/hora de inicio"},
                },
                "required": ["event_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_appointment",
            "description": "Cancela o elimina una cita específica",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "ID del evento a eliminar"}
                },
                "required": ["event_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_all_appointments",
            "description": "Elimina TODAS las citas futuras programadas del usuario",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Envía un correo electrónico a uno o varios destinatarios",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "array", 
                        "items": {"type": "string"},
                        "description": "Lista de correos de los destinatarios"
                    },
                    "subject": {"type": "string", "description": "Asunto del correo"},
                    "body": {"type": "string", "description": "Contenido del correo (puedes usar saltos de línea \\n)"}
                },
                "required": ["to", "subject", "body"]
            }
        }
    }
]
