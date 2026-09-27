import os
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@fast_db:5432/mafia_app"
)
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine)

Base = declarative_base()