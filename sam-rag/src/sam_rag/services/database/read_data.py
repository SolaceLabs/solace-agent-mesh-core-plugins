import logging
from typing import List, Tuple
from sqlalchemy.orm import Session

from sam_rag.services.database.connect import get_db
from sam_rag.services.database.model import Document, StatusEnum

log = logging.getLogger(__name__)

def read_document_data(db: Session) -> List[Tuple[str, str, StatusEnum, str]]:
    """
    Read path, file, status, and timestamp columns from the Document table.

    :param db: SQLAlchemy database session
    :return: List of tuples containing path, file, status, and timestamp values
    """
    try:
        results = db.query(
            Document.path, Document.file, Document.status, Document.timestamp
        ).all()
        log.info("Successfully read %d rows from the database", len(results))
        return results
    except Exception:
        log.exception("Error reading from database.")
        return []


def main():
    db = get_db()
    try:
        data = read_document_data(db)
        for path, file, status, timestamp in data:
            log.info(
                "Path: %s, File: %s, Status: %s, Timestamp: %s", path, file, status.value, timestamp
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
