from typing import Dict

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy import inspect
from datetime import datetime
from solace_ai_connector.common.log import log

from .model import Document, StatusEnum, config_db

SessionLocal = None


def get_db() -> Session:
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


def insert_document(db: Session, path: str, file: str, status: StatusEnum) -> Document:
    doc = Document(path=path, file=file, status=status, timestamp=datetime.now())
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def update_document(db: Session, path: str, status: StatusEnum) -> Document:
    doc = db.query(Document).filter(Document.path == path).first()
    if doc:
        doc.status = status
        doc.timestamp = datetime.now()
        db.commit()
        db.refresh(doc)
    return doc


def delete_document(db: Session, path: str) -> Document:
    doc = db.query(Document).filter(Document.path == path).first()
    if doc:
        db.delete(doc)
        db.commit()
    return doc


def connect(config: Dict = {}) -> Session:
    global SessionLocal
    db_url = config_db(config)
    if not db_url:
        raise ValueError("Database configuration not found.") from None
    try:
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

        # Test the connection
        if not inspect(engine).get_table_names():
            raise RuntimeError("Failed to establish a database connection.") from None

        log.info("Database connected")
        return SessionLocal
    except Exception:
        raise RuntimeError("Failed to initialize the database.") from None
