"""
Explicit database initialization script.
Creates tables and verifies extensions (e.g. pgvector on PostgreSQL).
Usage:
    python -m app.scripts.init_db
"""
import logging
from app.database.db import init_db as run_init_db, engine
import app.database.models  # Ensure all models are registered on Base.metadata

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_db")

def init_db():
    logger.info("Initializing database schema on dialect '%s'...", engine.dialect.name)
    run_init_db()
    logger.info("Database schema initialized successfully.")

if __name__ == "__main__":
    init_db()
