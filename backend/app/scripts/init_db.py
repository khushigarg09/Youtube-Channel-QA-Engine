"""
Explicit database initialization script.
Creates all SQLite tables defined in SQLAlchemy models.
Usage:
    python -m app.scripts.init_db
"""
import logging
from app.database.db import engine, Base
import app.database.models  # Ensure all models are registered on Base.metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_db")

def init_db():
    logger.info("Creating SQLite database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("SQLite database tables created successfully.")

if __name__ == "__main__":
    init_db()
