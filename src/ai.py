import json
import logging
import anthropic
from datetime import datetime
from src.config import ANTHROPIC_API_KEY, OPENAI_API_KEY, TIMEZONE_STR, TIMEZONE

logger = logging.getLogger(__name__)

# Anthropic client (primary)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# OpenAI client (optional — only for Whisper audio transcription)
try:
    import openai as _openai
    _openai_client = _openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
except Exception:
    _openai_client = None


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


# ---------------------------------------------------------------------------
# Format converters: OpenAI ↔ Anthropic
# ---------------------------------------------------------------------------

def _convert_tools_to_anthropic(openai_tools):
    """Convert OpenAI-style tool definitions to Anthropic format."""
    result = []
    for t in openai_tools:
        fn = t["function"]
        result.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def _convert_messages_to_anthropic(openai_messages):
    """
    Convert a list of OpenAI-format messages to Anthropic format.

    Key differences:
    - Anthropic: system prompt is separate (not in messages list)
    - Anthropic: tool results go as 'user' role, not 'tool' role
    - Anthropic: consecutive tool results must be grouped into one user message
    - Anthropic: assistant tool-use content is a list of blocks, not tool_calls
    """
    result = []
    i = 0

    while i < len(openai_messages):
        msg = openai_messages[i]
        role = msg.get("role")

        if role == "user":
            content = msg.get("content") or ""
            result.append({"role": "user", "content": content})
            i += 1

        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # Build assistant content block list
                content_blocks = []
                text = msg.get("content")
                if text:
                    content_blocks.append({"type": "text", "text": text})

                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = tc.get("id", "")
                        fn = tc.get("function", {})
                        name = fn.get("name", "")
                        arguments = fn.get("arguments", "{}")
                    else:
                        tc_id = tc.id
                        name = tc.function.name
                        arguments = tc.function.arguments

                    try:
                        input_data = json.loads(arguments) if isinstance(arguments, str) else arguments
                    except Exception:
                        input_data = {}

                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc_id,
                        "name": name,
                        "input": input_data,
                    })

                result.append({"role": "assistant", "content": content_blocks})

                # Collect all consecutive tool results and group into one user message
                tool_result_blocks = []
                j = i + 1
                while j < len(openai_messages) and openai_messages[j].get("role") == "tool":
                    tr = openai_messages[j]
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tr.get("tool_call_id", ""),
                        "content": tr.get("content") or "",
                    })
                    j += 1

                if tool_result_blocks:
                    result.append({"role": "user", "content": tool_result_blocks})
                    i = j
                else:
                    i += 1
            else:
                content = msg.get("content") or ""
                result.append({"role": "assistant", "content": content})
                i += 1

        elif role == "tool":
            # Orphaned tool message — skip (shouldn't happen in well-formed history)
            i += 1
        else:
            i += 1

    # Anthropic requires the first message to be 'user'
    while result and result[0]["role"] != "user":
        result.pop(0)

    return result


# ---------------------------------------------------------------------------
# Adapter stubs (keep bot.py unchanged)
# ---------------------------------------------------------------------------

class _FunctionStub:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments  # JSON string, matching OpenAI API


class _ToolCallStub:
    def __init__(self, id: str, name: str, arguments: str):
        self.id = id
        self.function = _FunctionStub(name, arguments)


class _MessageStub:
    """Makes Anthropic response look identical to openai.types.chat.ChatCompletionMessage."""

    def __init__(self, content: str, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls  # list of _ToolCallStub or None

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
        self.model = "claude-3-5-sonnet-20241022"

    def transcribe_audio(self, audio_file_path: str) -> str:
        if not _openai_client:
            return "No se pudo transcribir el audio (servicio de transcripción no disponible)."
        with open(audio_file_path, "rb") as f:
            transcript = _openai_client.audio.transcriptions.create(model="whisper-1", file=f)
        return transcript.text

    def get_agent_response(self, messages: list, tools: list) -> _MessageStub:
        anthropic_tools = _convert_tools_to_anthropic(tools)
        anthropic_messages = _convert_messages_to_anthropic(messages)

        if not anthropic_messages:
            return _MessageStub("No recibí ningún mensaje.")

        response = anthropic_client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=get_system_prompt(),
            messages=anthropic_messages,
            tools=anthropic_tools,
        )

        text_content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_content = block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    _ToolCallStub(
                        id=block.id,
                        name=block.name,
                        arguments=json.dumps(block.input),
                    )
                )

        logger.info(f"Claude response — stop_reason: {response.stop_reason}, tools: {len(tool_calls)}")
        return _MessageStub(
            content=text_content,
            tool_calls=tool_calls if tool_calls else None,
        )


# ---------------------------------------------------------------------------
# TOOLS definition (OpenAI format — converted to Anthropic format on call)
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
