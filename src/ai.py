from datetime import datetime
import openai
from src.config import OPENAI_API_KEY, TIMEZONE_STR, TIMEZONE
import json

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def get_system_prompt():
    now_local = datetime.now(TIMEZONE)
    
    return f"""
Eres un asistente experto en gestión de citas para un consultorio. 
Tu única función es ayudar al usuario a agendar, reprogramar, consultar y cancelar citas.
No respondas preguntas generales que no tengan que ver con citas.

REGLAS CRÍTICAS:
1. La zona horaria actual es {TIMEZONE_STR}.
2. La fecha y hora actual es: {now_local.strftime('%A, %d de %B de %Y, %I:%M %p')}.
3. Si el usuario no especifica la duración, asume 1 hora.
4. Si falta información (como la hora o el motivo), pídela amablemente.
5. **IMPORTANTE: Siempre pide el correo electrónico de los asistentes antes de agendar una cita.** Explícales que es para enviarles la invitación oficial de Google Calendar. Puedes pedir varios correos si es necesario.
6. **Google Meet:** Si el usuario solicita un link de reunión o menciona "reunión virtual", activa `enable_meet=True`.
7. Siempre confirma los detalles (incluyendo los correos y si habrá link de Meet) antes de ejecutar la acción.
8. Habla de forma profesional y amable en español.
9. No listas citas pasadas como pendientes a menos que se pida el historial.

Herramientas disponibles:
- create_appointment: Para agendar nuevas citas.
- update_appointment: Para cambiar fecha, hora o título de una cita existente.
- list_appointments: Para ver qué citas hay programadas.
- delete_appointment: Para cancelar una cita específica.
- delete_all_appointments: Para borrar todas las citas futuras de una sola vez.
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
    }
]
