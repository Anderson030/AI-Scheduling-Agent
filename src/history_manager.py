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
                    role = rec.role
                    content = rec.content or ""
                    
                    if role == "assistant" and content.startswith("{"):
                        msg = json.loads(content)
                        # OpenAI requiere que 'content' sea string o null, 
                        # pero a veces falla si es null explícito en el dict enviado.
                        if msg.get("content") is None:
                            msg["content"] = ""
                    else:
                        msg = {"role": role, "content": content}
                        if role == "tool":
                            msg["tool_call_id"] = rec.tool_call_id
                            msg["name"] = rec.name
                    
                    # Validación de seguridad: no agregar mensajes vacíos que rompan la API
                    if not msg.get("content") and not msg.get("tool_calls") and role != "tool":
                        continue
                        
                    messages.append(msg)
                except Exception as e:
                    logger.error(f"Error parseando mensaje de historial: {e}")

            # Truncado inteligente:
            # Nunca debemos empezar con un mensaje de rol 'tool' o 'assistant' que tenga tool_calls incompleto.
            # La forma más segura de truncar es asegurar que el primer mensaje sea de tipo 'user'.
            if len(messages) > limit:
                # Nos quedamos con los últimos 'limit' mensajes
                messages = messages[-limit:]
                # Seguimos eliminando desde el principio hasta que el primer mensaje sea 'user'
                while messages and messages[0].get("role") != "user":
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
            content_to_save = content or ""
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

    @staticmethod
    def delete_user_history(user_id: str):
        """Elimina todo el historial de un usuario"""
        db = SessionLocal()
        try:
            db.query(ConversationHistory).filter(ConversationHistory.telegram_id == user_id).delete()
            db.commit()
        finally:
            db.close()
