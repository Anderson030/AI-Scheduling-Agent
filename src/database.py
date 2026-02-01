from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

# TEMPORAL: Usar SQLite para evitar problemas de encoding de psycopg2 en Windows
# Para producción, cambiar a PostgreSQL cuando se resuelva el problema de encoding
USE_SQLITE = os.getenv("USE_SQLITE", "true").lower() == "true"

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL")

if USE_SQLITE or not DATABASE_URL:
    if not DATABASE_URL and not USE_SQLITE:
        print("Warning: DATABASE_URL not found, falling back to SQLite.")
    
    DATABASE_URL = "sqlite:///./scheduling_agent.db"
    engine = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False},
        pool_pre_ping=True
    )
else:
    # Soporte para Railway (cambia postgres:// a postgresql:// si es necesario)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, index=True)
    event_id = Column(String, unique=True, index=True)
    title = Column(String)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    rem_24h_sent = Column(Boolean, default=False)
    rem_3h_sent = Column(Boolean, default=False)
    rem_1h_sent = Column(Boolean, default=False)
    rem_15m_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class UserAuth(Base):
    __tablename__ = "user_auth"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, unique=True, index=True)
    access_token = Column(String)
    refresh_token = Column(String)
    token_uri = Column(String)
    client_id = Column(String)
    client_secret = Column(String)
    scopes = Column(String)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(String, index=True)
    role = Column(String) # user, assistant, tool
    content = Column(String)
    tool_call_id = Column(String, nullable=True)
    name = Column(String, nullable=True) # for tool messages
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
