import sys
from src.ai import AIService
import os
from src.config import OPENAI_API_KEY

def test_multilingual():
    # Asegurar que la salida use UTF-8 para evitar errores en Windows
    if sys.stdout.encoding != 'utf-8':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    if not OPENAI_API_KEY:
        print("Saltando prueba: OPENAI_API_KEY no encontrada.")
        return

    ai = AIService()
    
    print("Probando respuesta en inglés...")
    messages_en = [{"role": "user", "content": "Hello, I want to see my appointments for today."}]
    response_en = ai.get_agent_response(messages_en, [])
    print(f"Respuesta (EN): {response_en.content}")
    
    print("\nProbando respuesta en español...")
    messages_es = [{"role": "user", "content": "Hola, ¿qué eventos tengo hoy?"}]
    response_es = ai.get_agent_response(messages_es, [])
    print(f"Respuesta (ES): {response_es.content}")

if __name__ == "__main__":
    test_multilingual()
