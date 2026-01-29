from sqlalchemy import create_all, create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from src.config import DATABASE_URL
import datetime

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
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
