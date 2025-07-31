from typing import List, Tuple
from sqlalchemy.orm import Session
from solace_ai_connector.common.log import log

from sam_rag.services.database.connect import get_db
from sam_rag.services.database.model import Document, StatusEnum


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
        log.info(f"Successfully read {len(results)} rows from the database")
        return results
    except Exception as e:
        log.error(f"Error reading from database.", trace=e)
        return []


def main():
    db = get_db()
    try:
        data = read_document_data(db)
        for path, file, status, timestamp in data:
            log.info(
                f"Path: {path}, File: {file}, Status: {status.value}, Timestamp: {timestamp}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
