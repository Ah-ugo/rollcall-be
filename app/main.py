from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .core.database import init_indexes
from .routers import auth, classes, enrollment, attendance, reports

@asynccontextmanager
async def lifespan(app):
    await init_indexes()
    yield

app = FastAPI(title="Attendance API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.FRONTEND_URL], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth.router, classes.router, reports.router, enrollment.router, attendance.router):
    app.include_router(r, prefix="/api")

@app.get("/api/health")
def health(): return {"ok": True}
