import json
import logging
import pathlib
from google import genai
from google.genai import types
from datetime import datetime
from src.config import GEMINI_API_KEY, TIMEZONE_STR, TIMEZONE

logger = logging.getLogger(__name__)

client = genai.Client(api_key=GEMINI_API_KEY)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

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
6. **Google Meet:** Si el usuario solicita un link de reunión o menciona "reunión virtual", activa enable_meet=True.
7. Siempre confirma los detalles (correos y Meet) antes de ejecutar la acción.
8. **DETECCIÓN DE IDIOMA:** Detecta el idioma del usuario y responde siempre en el mismo idioma (principalmente español o inglés). Mantén un tono profesional y amable en cualquier idioma.
9. **Estilo Personalizado (Emojis):** Usa emojis sutiles para resaltar información importante (máximo 2 por mensaje).
    - Usa ✅ para confirmaciones exitosas.
    - Usa ℹ️ o ⚠️ para advertencias o información crítica.
    - Usa 👋 o 🗓️ para saludos y referencias al calendario.
10. No listes eventos pasados como pendientes a menos que se pida el historial.

Herramientas disponibles:
- create_appointment: Para agendar nuevos eventos.
- update_appointment: Para cambiar detalles de un evento.
- list_appointments: Para consultar eventos programados.
- delete_appointment: Para cancelar un evento.
- delete_all_appointments: Para borrar todos los eventos futuros.
- send_email: Para redactar y enviar correos electrónicos.

REGLAS DE CORREO ELECTRÓNICO:
1. Propón una redacción elegante en el idioma en que te estés comunicando con el usuario.
2. Muestra el Asunto y el Cuerpo antes de enviar y pide confirmación.
3. No uses send_email hasta que el usuario confirme tras ver la previsualización.
"""


# ---------------------------------------------------------------------------
# Format converters: OpenAI history → Gemini format
# ---------------------------------------------------------------------------

def _build_gemini_tools(openai_tools):
    """Convert OpenAI-style tool definitions to google-genai types.Tool."""
    function_declarations = []
    for t in openai_tools:
        fn = t["function"]
        params = fn.get("parameters", {"type": "object", "properties": {}})
        function_declarations.append(
            types.FunctionDeclaration(
                name=fn["name"],
                description=fn.get("description", ""),
                parameters=params,
            )
        )
    return [types.Tool(function_declarations=function_declarations)]


def _convert_messages_to_gemini(openai_messages):
    """
    Convert OpenAI-format message list to Gemini (google-genai) format.

    Gemini differences:
    - 'assistant' role → 'model'
    - tool_calls in assistant message → function_call parts
    - tool results → function_response parts grouped in a 'user' message
    - Must start with a 'user' message
    """
    result = []
    i = 0

    while i < len(openai_messages):
        msg = openai_messages[i]
        role = msg.get("role")

        if role == "user":
            content = msg.get("content") or ""
            result.append(types.Content(role="user", parts=[types.Part(text=content)]))
            i += 1

        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                parts = []
                text = msg.get("content")
                if text:
                    parts.append(types.Part(text=text))

                for tc in tool_calls:
                    if isinstance(tc, dict):
                        name = tc["function"]["name"]
                        arguments = tc["function"]["arguments"]
                    else:
                        name = tc.function.name
                        arguments = tc.function.arguments

                    try:
                        args = json.loads(arguments) if isinstance(arguments, str) else arguments
                    except Exception:
                        args = {}

                    parts.append(types.Part(function_call=types.FunctionCall(name=name, args=args)))

                result.append(types.Content(role="model", parts=parts))

                # Collect all consecutive tool results → one user message
                tool_result_parts = []
                j = i + 1
                while j < len(openai_messages) and openai_messages[j].get("role") == "tool":
                    tr = openai_messages[j]
                    content_str = tr.get("content") or ""
                    try:
                        content_val = json.loads(content_str)
                    except Exception:
                        content_val = {"result": content_str}

                    tool_result_parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=tr.get("name", "unknown"),
                                response=content_val,
                            )
                        )
                    )
                    j += 1

                if tool_result_parts:
                    result.append(types.Content(role="user", parts=tool_result_parts))
                    i = j
                else:
                    i += 1
            else:
                content = msg.get("content") or ""
                result.append(types.Content(role="model", parts=[types.Part(text=content)]))
                i += 1

        elif role == "tool":
            # Orphaned tool message — skip
            i += 1
        else:
            i += 1

    # Gemini requires the first message to be 'user'
    while result and result[0].role != "user":
        result.pop(0)

    return result


# ---------------------------------------------------------------------------
# Adapter stubs (keeps bot.py unchanged)
# ---------------------------------------------------------------------------

class _FunctionStub:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments  # JSON string


class _ToolCallStub:
    def __init__(self, id: str, name: str, arguments: str):
        self.id = id
        self.function = _FunctionStub(name, arguments)


class _MessageStub:
    """Makes Gemini response look identical to an OpenAI ChatCompletionMessage."""

    def __init__(self, content: str, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self):
        if self.tool_calls:
            return {
                "role": "assistant",
                "content": self.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in self.tool_calls
                ],
            }
        return {"role": "assistant", "content": self.content or ""}


# ---------------------------------------------------------------------------
# AIService
# ---------------------------------------------------------------------------

class AIService:
    def __init__(self):
        self.model_name = "gemini-2.5-flash"

    def transcribe_audio(self, audio_file_path: str) -> str:
        """Transcribe audio using Gemini multimodal API."""
        try:
            audio_bytes = pathlib.Path(audio_file_path).read_bytes()
            response = client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                    "Transcribe exactly what is said in this audio. Return only the transcription, no extra commentary.",
                ],
            )
            return response.text.strip()
        except Exception as e:
            logger.warning(f"Audio transcription unavailable: {e}")
            return "No se pudo transcribir el audio (servicio no disponible)."

    def get_agent_response(self, messages: list, tools: list) -> _MessageStub:
        gemini_tools = _build_gemini_tools(tools)
        gemini_messages = _convert_messages_to_gemini(messages)

        if not gemini_messages:
            return _MessageStub("No recibí ningún mensaje.")

        config = types.GenerateContentConfig(
            system_instruction=get_system_prompt(),
            tools=gemini_tools,
        )

        response = client.models.generate_content(
            model=self.model_name,
            contents=gemini_messages,
            config=config,
        )

        text_content = ""
        tool_calls = []

        parts = response.candidates[0].content.parts or []

        for part in parts:
            if hasattr(part, "text") and part.text:
                text_content += part.text
            elif hasattr(part, "function_call") and part.function_call and part.function_call.name:
                fc = part.function_call
                tool_calls.append(
                    _ToolCallStub(
                        id=f"call_{fc.name}_{len(tool_calls)}",
                        name=fc.name,
                        arguments=json.dumps(fc.args if fc.args else {}),
                    )
                )

        logger.info(f"Gemini response — tool_calls: {len(tool_calls)}, text_len: {len(text_content)}")
        return _MessageStub(
            content=text_content,
            tool_calls=tool_calls if tool_calls else None,
        )


# ---------------------------------------------------------------------------
# TOOLS (OpenAI format — converted to Gemini format on each call)
# ---------------------------------------------------------------------------

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
                        "description": "Lista de correos electrónicos de los asistentes",
                    },
                    "enable_meet": {"type": "boolean", "description": "¿Generar un enlace de Google Meet?"},
                },
                "required": ["summary", "start_time", "user_emails"],
            },
        },
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
                },
            },
        },
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
                "required": ["event_id"],
            },
        },
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
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_all_appointments",
            "description": "Elimina TODAS las citas futuras programadas del usuario",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
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
                        "description": "Lista de correos de los destinatarios",
                    },
                    "subject": {"type": "string", "description": "Asunto del correo"},
                    "body": {"type": "string", "description": "Contenido del correo"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
]
