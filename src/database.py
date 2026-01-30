from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

# TEMPORAL: Usar SQLite para evitar problemas de encoding de psycopg2 en Windows
# Para producción, cambiar a PostgreSQL cuando se resuelva el problema de encoding
USE_SQLITE = os.getenv("USE_SQLITE", "true").lower() == "true"

if USE_SQLITE:
    DATABASE_URL = "sqlite:///./scheduling_agent.db"
    engine = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False},
        pool_pre_ping=True
    )
else:
    # PostgreSQL (tiene problemas de encoding en Windows con caracteres especiales)
    DB_USER = os.getenv("DB_USER", "scheduling_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "secure_password_123")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "scheduling_db")
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(
        DATABASE_URL,
        connect_args={'client_encoding': 'utf8'},
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

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
