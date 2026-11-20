import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .core.database import init_indexes
from .routers import auth, classes, enrollment, attendance, reports

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app):
    await init_indexes()
    # Pre-load the InsightFace model at startup so the first verify request
    # never blocks waiting for a cold model load.
    logger.info("Pre-loading InsightFace model...")
    from .services import face_service
    await asyncio.to_thread(face_service._model)
    logger.info("InsightFace model ready.")
    yield

app = FastAPI(title="Attendance API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.FRONTEND_URL], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, classes.router, reports.router, enrollment.router, attendance.router):
    app.include_router(r, prefix="/api")

@app.get("/api/health")
def health(): return {"ok": True}
