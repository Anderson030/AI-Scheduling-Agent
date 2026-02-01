import logging
import json
from src.database import SessionLocal, ConversationHistory

logger = logging.getLogger(__name__)

class HistoryManager:
    @staticmethod
    def get_user_history(user_id: str, limit: int = 15):
        """Recupera el historial de mensajes de la base de datos para un usuario"""
        db = SessionLocal()
        try:
            records = db.query(ConversationHistory).filter(
                ConversationHistory.telegram_id == user_id
            ).order_by(ConversationHistory.created_at.asc()).all()
            
            messages = []
            for rec in records:
                try:
                    # Si el contenido empieza como JSON, es un mensaje de assistant con tool_calls
                    if rec.role == "assistant" and rec.content.startswith("{"):
                        msg = json.loads(rec.content)
                    else:
                        msg = {"role": rec.role, "content": rec.content}
                        if rec.role == "tool":
                            msg["tool_call_id"] = rec.tool_call_id
                            msg["name"] = rec.name
                    messages.append(msg)
                except Exception as e:
                    logger.error(f"Error parseando mensaje de historial: {e}")
                    messages.append({"role": rec.role, "content": rec.content})

            # Truncado inteligente (evitar que empiece con 'tool')
            if len(messages) > limit:
                messages = messages[-limit:]
                while messages and messages[0].get("role") == "tool":
                    messages.pop(0)
            
            return messages
        finally:
            db.close()

    @staticmethod
    def save_message(user_id: str, role: str, content: str, tool_call_id: str = None, name: str = None):
        """Guarda un nuevo mensaje en el historial persistente"""
        db = SessionLocal()
        try:
            # Si el contenido es un dict (assistant message dump), lo serializamos
            content_to_save = content
            if isinstance(content, dict):
                content_to_save = json.dumps(content)
                
            new_msg = ConversationHistory(
                telegram_id=user_id,
                role=role,
                content=content_to_save,
                tool_call_id=tool_call_id,
                name=name
            )
            db.add(new_msg)
            db.commit()
        finally:
            db.close()
