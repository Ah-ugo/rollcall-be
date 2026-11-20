import bcrypt, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .config import settings
from .database import db, oid

bearer = HTTPBearer(auto_error=False)

def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()

def verify_password(p: str, h: str) -> bool:
    return bcrypt.checkpw(p.encode(), h.encode())

def create_token(lecturer_id: str) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    return jwt.encode({"sub": lecturer_id, "exp": exp}, settings.JWT_SECRET, algorithm="HS256")

def decode_token(token: str) -> str:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])["sub"]
    except Exception:
        raise HTTPException(401, "Invalid or expired token")

async def current_lecturer(cred: HTTPAuthorizationCredentials = Depends(bearer)):
    if not cred:
        raise HTTPException(401, "Not authenticated")
    lec = await db.lecturers.find_one({"_id": oid(decode_token(cred.credentials))})
    if not lec:
        raise HTTPException(401, "Account not found")
    return lec

async def owned_class(class_id: str, lecturer):
    """Ownership check: a lecturer can only touch their own classes."""
    c = await db.classes.find_one({"_id": oid(class_id), "lecturer_id": lecturer["_id"]})
    if not c:
        raise HTTPException(404, "Class not found")
    return c

async def owned_session(session_id: str, lecturer):
    s = await db.attendance_sessions.find_one({"_id": oid(session_id), "lecturer_id": lecturer["_id"]})
    if not s:
        raise HTTPException(404, "Session not found")
    return s
