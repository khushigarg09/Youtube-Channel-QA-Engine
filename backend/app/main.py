import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database.db import SessionLocal
from app.database.models import Video, Channel
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
    - Startup Self-Healing: automatically identifies and resets any channels and videos left
      in 'indexing' or 'cancel_requested' state due to prior server terminations/crashes.
    """
    # ── Startup Self-Healing ──
    try:
        with SessionLocal() as db:
            # Reset channels left in indexing or cancel_requested back to idle
            stuck_channels = db.query(Channel).filter(
                Channel.indexing_status.in_(["indexing", "cancel_requested"])
            ).update({"indexing_status": "idle"})

            # Reset videos left in indexing back to pending
            stuck_videos = db.query(Video).filter(Video.status == "indexing").update({"status": "pending"})
            db.commit()

            if stuck_channels > 0:
                logger.info(f"Self-Healing: Reset {stuck_channels} stuck channel(s) back to 'idle'.")
            if stuck_videos > 0:
                logger.info(f"Self-Healing: Reset {stuck_videos} stuck 'indexing' video(s) back to 'pending'.")
            if stuck_channels == 0 and stuck_videos == 0:
                logger.info("Self-Healing check: No orphaned indexing jobs found.")
    except Exception as e:
        logger.error(f"Error during startup self-healing check: {e}")

    yield

    logger.info("Shutting down YouTube Channel QA Engine API.")


def create_app(lifespan_context=lifespan) -> FastAPI:
    app = FastAPI(
        title="YouTube Channel QA Engine API",
        description="Local RAG engine for channel-wide YouTube indexing, hybrid search, and citation QA.",
        version="2.0.0",
        lifespan=lifespan_context,
    )

    # Register rate limiter state and exception handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Enable CORS for frontend API calls
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
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
                "Hybrid BM25 + Vector RAG with True RRF",
                "Dynamic Keyphrase Topic Discovery",
                "Bounded Scope Channel Indexing",
                "Single-Video Re-indexing with Vector Cleanup",
                "JSON/CSV Transcript Exports",
                "Rate-Limited Streaming Chat"
            ]
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
