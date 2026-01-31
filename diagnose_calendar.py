
import sys
import os
from datetime import datetime
# Añadir el path actual para poder importar src
sys.path.append(os.getcwd())

from src.calendar_api import CalendarService

def diagnose():
    service = CalendarService()
    print(f"Buscando eventos en el calendario: {os.getenv('CALENDAR_ID', 'primary')}")
    print(f"Fecha actual (UTC): {datetime.utcnow().isoformat()}Z")
    
    # Probar comportamiento por defecto
    print("\n--- Comportamiento por defecto (time_min=None) ---")
    events = service.list_events(time_min=None, max_results=10)
    
    if not events:
        print("No se encontraron eventos futuros.")
    else:
        print(f"Se encontraron {len(events)} eventos futuros:")
        for i, event in enumerate(events, 1):
            start = event['start'].get('dateTime') or event['start'].get('date')
            print(f"{i}. {event['summary']} - Fecha: {start}")

    # Probar con fecha antigua para confirmar acceso
    print("\n--- Historial completo (time_min='2020-01-01T00:00:00Z') ---")
    events_all = service.list_events(time_min="2020-01-01T00:00:00Z", max_results=50)
    print(f"Total eventos en historial: {len(events_all)}")

if __name__ == "__main__":
    # Asegurarse de que las variables de entorno estén cargadas si es necesario
    # Aunque CalendarService las importa de src.config, que a su vez debería cargarlas de .env
    diagnose()
