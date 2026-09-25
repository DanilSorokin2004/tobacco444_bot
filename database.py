from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'tobacco444.db')}"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)

def init_db():
     Base.metadata.create_all(engine)

def get_session():
     return SessionLocal()