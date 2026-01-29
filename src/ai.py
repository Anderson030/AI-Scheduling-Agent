import openai
from src.config import OPENAI_API_KEY, TIMEZONE_STR
import json

client = openai.OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = f"""
Eres un asistente experto en gestión de citas para un consultorio. 
Tu única función es ayudar al usuario a agendar, reprogramar, consultar y cancelar citas.
No respondas preguntas generales que no tengan que ver con citas.

REGLAS CRÍTICAS:
1. La zona horaria actual es {TIMEZONE_STR}.
2. Si el usuario no especifica la duración, asume 1 hora.
3. Si falta información (como la hora o el motivo), pídela amablemente.
4. Siempre confirma los detalles antes de ejecutar una acción si hay ambigüedad.
5. Habla de forma profesional y amable en español.

Herramientas disponibles:
- create_appointment: Para agendar nuevas citas.
- update_appointment: Para cambiar fecha, hora o título de una cita existente.
- list_appointments: Para ver qué citas hay programadas.
- delete_appointment: Para cancelar una cita.
"""

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
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            tools=tools,
            tool_choice="auto"
        )
        return response.choices[0].message

# Definición de herramientas para OpenAI
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
                },
                "required": ["summary", "start_time"]
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
            "description": "Cancela o elimina una cita",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {"type": "string", "description": "ID del evento a eliminar"}
                },
                "required": ["event_id"]
            }
        }
    }
]
