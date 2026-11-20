from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from datetime import datetime
from .config import settings

client = AsyncIOMotorClient(settings.MONGO_URL)
db = client[settings.DB_NAME]

async def init_indexes():
    await db.lecturers.create_index("email", unique=True)
    await db.classes.create_index("lecturer_id")
    await db.classes.create_index("enrol_token", unique=True)
    await db.class_enrollments.create_index([("class_id", 1), ("matric_no", 1)], unique=True)
    await db.attendance_sessions.create_index("token", unique=True)
    await db.attendance_records.create_index([("session_id", 1), ("enrollment_id", 1)], unique=True)
    await db.attendance_attempts.create_index("session_id")

def oid(value: str) -> ObjectId:
    from fastapi import HTTPException
    try:
        return ObjectId(value)
    except Exception:
        raise HTTPException(404, "Not found")

def ser(doc):
    """Make a Mongo document JSON-safe; never leak embeddings or password hashes."""
    if doc is None:
        return None
    out = {}
    for k, v in doc.items():
        if k in ("embedding", "password_hash"):
            continue
        if k == "_id":
            out["id"] = str(v)
        elif isinstance(v, ObjectId):
            out[k] = str(v)
        elif isinstance(v, datetime):
            out[k] = v.isoformat() + "Z"
        else:
            out[k] = v
    return out
