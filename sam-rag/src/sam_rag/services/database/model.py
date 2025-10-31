import enum
import logging
from typing import Dict
from sqlalchemy import create_engine, Column, String, Enum, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

log = logging.getLogger(__name__)

class StatusEnum(enum.Enum):
    modified = "modified"
    deleted = "deleted"
    new = "new"


class Document(Base):
    __tablename__ = "document"

    path = Column(String, primary_key=True)
    file = Column(String, nullable=False)
    status = Column(Enum(StatusEnum), nullable=False)
    timestamp = Column(DateTime, default=datetime.now())


def config_db(config: Dict = {}):
    """Configure the database with the specified configuration."""
    db_url = None
    if config:
        db_type = config.get("type")
        if db_type == "sqlite":
            db_url = f"sqlite:///{config.get('path', 'scanner.db')}"
        elif db_type == "postgresql":
            db_url = f"postgresql://{config.get('user')}:{config.get('password')}@{config.get('host')}:{config.get('port')}/{config.get('dbname')}"
    return db_url


def init_db(config: Dict = {}):
    """Initialize the database with the specified configuration."""

    db_url = config_db(config)
    if not db_url:
        raise ValueError("Database configuration not found.") from None

    try:
        log.debug("Initializing the database...")
        engine = create_engine(db_url)
        Base.metadata.create_all(bind=engine)
    except Exception:
        raise RuntimeError("Failed to initialize the database") from None
