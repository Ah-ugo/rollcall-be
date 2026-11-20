from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from ..core.config import settings
from ..core.database import db, ser
from ..core.security import current_lecturer, owned_class, owned_session, decode_token
from ..services import face_service
from ..services.location_service import haversine_m
from ..services.qr_service import new_token, qr_data_url
from ..services.ws_manager import manager

router = APIRouter(tags=["attendance"])

def naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo:
        from datetime import timezone
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt

def session_status(s) -> str:
    now = datetime.utcnow()
    if s.get("cancelled"): return "cancelled"
    if s.get("closed_manually"): return "closed"
    if now < s["start_time"]: return "not_started"
    if now > s["end_time"]: return "ended"
    return "open"

class SessionIn(BaseModel):
    title: str = Field(min_length=2, max_length=150)
    start_time: datetime
    end_time: datetime
    venue: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0, le=5000)

class SessionPatch(BaseModel):
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    venue: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_m: Optional[float] = None
    action: Optional[str] = None  # cancel | close

def attend_url(token): return f"{settings.FRONTEND_URL}/attendance/{token}"

async def session_out(s, with_qr=False):
    d = ser(s)
    d["status"] = session_status(s)
    d["url"] = attend_url(s["token"])
    d["enrolled"] = await db.class_enrollments.count_documents({"class_id": s["class_id"]})
    d["present"] = await db.attendance_records.count_documents({"session_id": s["_id"]})
    d["failed"] = await db.attendance_attempts.count_documents({"session_id": s["_id"], "success": False})
    if with_qr:
        d["qr"] = qr_data_url(d["url"])
        c = await db.classes.find_one({"_id": s["class_id"]})
        d["course_code"], d["course_title"] = c["course_code"], c["course_title"]
    return d

@router.post("/classes/{class_id}/sessions")
async def create_session(class_id: str, body: SessionIn, lec=Depends(current_lecturer)):
    c = await owned_class(class_id, lec)
    st, et = naive_utc(body.start_time), naive_utc(body.end_time)
    if et <= st:
        raise HTTPException(400, "Closing time must be after opening time")
    doc = {"class_id": c["_id"], "lecturer_id": lec["_id"], "token": new_token(), "title": body.title.strip(),
           "start_time": st, "end_time": et, "venue": body.venue, "latitude": body.latitude,
           "longitude": body.longitude, "radius_m": body.radius_m, "cancelled": False,
           "closed_manually": False, "created_at": datetime.utcnow()}
    res = await db.attendance_sessions.insert_one(doc)
    doc["_id"] = res.inserted_id
    return await session_out(doc, True)

@router.get("/classes/{class_id}/sessions")
async def list_sessions(class_id: str, lec=Depends(current_lecturer)):
    c = await owned_class(class_id, lec)
    cur = db.attendance_sessions.find({"class_id": c["_id"]}).sort("start_time", -1)
    return [await session_out(s) async for s in cur]

@router.get("/sessions/{session_id}")
async def get_session(session_id: str, lec=Depends(current_lecturer)):
    s = await owned_session(session_id, lec)
    out = await session_out(s, True)
    present = {r["enrollment_id"]: r async for r in db.attendance_records.find({"session_id": s["_id"]})}
    roster = []
    async for e in db.class_enrollments.find({"class_id": s["class_id"]}).sort("full_name", 1):
        r = present.get(e["_id"])
        roster.append({"id": str(e["_id"]), "full_name": e["full_name"], "matric_no": e["matric_no"],
                       "present": bool(r), "time": r["created_at"].isoformat() + "Z" if r else None,
                       "distance_m": r.get("distance_m") if r else None})
    out["roster"] = roster
    return out

@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, body: SessionPatch, lec=Depends(current_lecturer)):
    s = await owned_session(session_id, lec)
    upd = {}
    if body.action == "cancel": upd["cancelled"] = True
    elif body.action == "close": upd["closed_manually"] = True
    else:
        if session_status(s) != "not_started":
            raise HTTPException(400, "Sessions can only be edited before they open")
        for k, v in body.model_dump(exclude={"action"}).items():
            if v is not None:
                upd[k] = naive_utc(v) if isinstance(v, datetime) else v
    if upd:
        await db.attendance_sessions.update_one({"_id": s["_id"]}, {"$set": upd})
        await db.audit_logs.insert_one({"lecturer_id": lec["_id"], "action": "session_updated",
                                        "target": session_id, "changes": {k: str(v) for k, v in upd.items()},
                                        "at": datetime.utcnow()})
    return await session_out(await db.attendance_sessions.find_one({"_id": s["_id"]}), True)

@router.get("/sessions/{session_id}/attempts")
async def attempts(session_id: str, lec=Depends(current_lecturer)):
    s = await owned_session(session_id, lec)
    return [ser(a) async for a in db.attendance_attempts.find({"session_id": s["_id"]}).sort("created_at", -1).limit(200)]

@router.websocket("/ws/sessions/{session_id}")
async def ws_session(ws: WebSocket, session_id: str, token: str):
    try:
        lid = decode_token(token)
        s = await db.attendance_sessions.find_one({"_id": __import__("bson").ObjectId(session_id)})
        assert s and str(s["lecturer_id"]) == lid
    except Exception:
        await ws.close(code=4401); return
    await manager.join(session_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.leave(session_id, ws)

# ---------------- Student-facing ----------------
@router.get("/public/attend/{token}")
async def public_session(token: str):
    s = await db.attendance_sessions.find_one({"token": token})
    if not s:
        raise HTTPException(404, "This attendance link is invalid")
    c = await db.classes.find_one({"_id": s["class_id"]})
    return {"course_code": c["course_code"], "course_title": c["course_title"], "title": s["title"],
            "venue": s["venue"], "status": session_status(s),
            "start_time": s["start_time"].isoformat() + "Z", "end_time": s["end_time"].isoformat() + "Z"}

class VerifyIn(BaseModel):
    matric_no: str
    images: List[str] = Field(min_length=1, max_length=3)  # live frames captured during the liveness prompt
    latitude: float
    longitude: float
    accuracy: float

async def _log(s, matric, enr, success, reason, **extra):
    doc = {"session_id": s["_id"], "matric_no": matric, "enrollment_id": enr["_id"] if enr else None,
           "full_name": enr["full_name"] if enr else None, "success": success, "reason": reason,
           "created_at": datetime.utcnow(), **extra}
    await db.attendance_attempts.insert_one(doc)
    await manager.broadcast(str(s["_id"]), {"type": "attempt", "attempt": ser(dict(doc)),
                                            "present": await db.attendance_records.count_documents({"session_id": s["_id"]}),
                                            "failed": await db.attendance_attempts.count_documents({"session_id": s["_id"], "success": False})})

def _fail(code: str, msg: str, status=400):
    raise HTTPException(status, {"code": code, "message": msg})

@router.post("/public/attend/{token}/verify")
async def verify(token: str, body: VerifyIn):
    s = await db.attendance_sessions.find_one({"token": token})
    if not s:
        _fail("invalid_session", "This attendance link is invalid", 404)
    st = session_status(s)
    if st != "open":
        msgs = {"not_started": "Attendance has not opened yet", "ended": "Attendance for this session has closed",
                "closed": "The lecturer has closed this session", "cancelled": "This session was cancelled"}
        _fail(st, msgs[st], 403)
    matric = body.matric_no.strip().upper()
    enr = await db.class_enrollments.find_one({"class_id": s["class_id"], "matric_no": matric})
    if not enr:
        await _log(s, matric, None, False, "Not enrolled")
        _fail("not_enrolled", "This matriculation number is not enrolled in this class", 403)
    if await db.attendance_records.find_one({"session_id": s["_id"], "enrollment_id": enr["_id"]}):
        _fail("duplicate", "Attendance already recorded for this session", 409)

    # --- Facial verification (1:1) ---
    prof = await db.facial_profiles.find_one({"enrollment_id": enr["_id"]})
    try:
        embs = [face_service.embed(i) for i in body.images]
    except HTTPException as e:
        await _log(s, matric, enr, False, f"Face capture issue: {e.detail}")
        raise
    if len(embs) > 1 and min(face_service.similarity(embs[0], e) for e in embs[1:]) > 0.9995:
        await _log(s, matric, enr, False, "Liveness check failed")
        _fail("liveness", "Liveness check failed. Follow the on-screen prompt and try again.", 422)
    scores = [face_service.similarity(prof["embedding"], e) for e in embs]
    score = min(scores)
    if score < settings.FACE_THRESHOLD:
        await _log(s, matric, enr, False, "Face mismatch", similarity=round(score, 3))
        _fail("face_mismatch", "Your face does not match the profile registered for this number", 403)

    # --- Geolocation ---
    if body.accuracy > settings.MAX_GPS_ACCURACY_M:
        await _log(s, matric, enr, False, "Poor GPS accuracy", accuracy=body.accuracy)
        _fail("poor_gps", f"Location is too imprecise (±{round(body.accuracy)} m). Move near a window or outdoors and retry.", 422)
    dist = haversine_m(body.latitude, body.longitude, s["latitude"], s["longitude"])
    if dist > s["radius_m"]:
        await _log(s, matric, enr, False, "Outside radius", distance_m=round(dist), similarity=round(score, 3))
        _fail("outside_radius", f"You are about {round(dist)} m from the venue. The limit is {round(s['radius_m'])} m.", 403)

    try:
        await db.attendance_records.insert_one({"session_id": s["_id"], "class_id": s["class_id"],
            "enrollment_id": enr["_id"], "matric_no": matric, "similarity": round(score, 3),
            "distance_m": round(dist), "accuracy": body.accuracy, "created_at": datetime.utcnow()})
    except DuplicateKeyError:
        _fail("duplicate", "Attendance already recorded for this session", 409)
    await _log(s, matric, enr, True, "Verified", similarity=round(score, 3), distance_m=round(dist))
    return {"ok": True, "full_name": enr["full_name"], "distance_m": round(dist)}
