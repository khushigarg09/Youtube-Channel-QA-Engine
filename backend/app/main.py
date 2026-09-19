import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database.db import engine, Base, SessionLocal
from app.database.models import Video
from app.api.router import router, limiter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI Lifespan Context:
    - Creates database schemas on startup.
    - Self-healing: automatically identifies and resets any videos left in 'indexing'
      state due to prior server terminations/crashes.
    """
    logger.info("Initializing SQLite database tables...")
    Base.metadata.create_all(bind=engine)

    # ── Startup Self-Healing ──
    try:
        with SessionLocal() as db:
            stuck_count = db.query(Video).filter(Video.status == "indexing").update({"status": "pending"})
            db.commit()
            if stuck_count > 0:
                logger.info(f"Self-Healing: Reset {stuck_count} stuck 'indexing' video(s) back to 'pending'.")
            else:
                logger.info("Self-Healing check: No orphaned indexing jobs found.")
    except Exception as e:
        logger.error(f"Error during startup self-healing check: {e}")

    yield

    logger.info("Shutting down YouTube Knowledge Graph API.")


app = FastAPI(
    title="YouTube Channel QA Engine API",
    description="Production-grade RAG engine for channel-wide YouTube indexing, hybrid search, and citation QA.",
    version="2.0.0",
    lifespan=lifespan
)

# Register rate limiter state and exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Enable CORS for frontend API calls
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(router, prefix="/api")


@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "YouTube Channel QA Engine API",
        "version": "2.0.0",
        "db_type": "SQLite",
        "vector_store": "ChromaDB",
        "features": [
            "Lifespan Self-Healing",
            "Hybrid BM25 + Vector RAG",
            "Dynamic Keyphrase Topic Discovery",
            "Single-Video Re-indexing",
            "JSON/CSV Transcript Exports",
            "Rate-Limited Streaming Chat"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
