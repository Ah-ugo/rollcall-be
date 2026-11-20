from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from ..core.database import db, ser, oid
from ..core.security import current_lecturer, owned_class
from ..services.qr_service import new_token
from .attendance import session_status

router = APIRouter(prefix="/classes", tags=["classes"])

class ClassIn(BaseModel):
    course_code: str = Field(min_length=2, max_length=20)
    course_title: str = Field(min_length=2, max_length=150)
    description: Optional[str] = ""

class ClassPatch(BaseModel):
    course_code: Optional[str] = None
    course_title: Optional[str] = None
    description: Optional[str] = None
    enrolment_open: Optional[bool] = None
    archived: Optional[bool] = None

class StudentPatch(BaseModel):
    full_name: Optional[str] = None
    matric_no: Optional[str] = None

async def class_out(c):
    d = ser(c)
    d["student_count"] = await db.class_enrollments.count_documents({"class_id": c["_id"]})
    d["session_count"] = await db.attendance_sessions.count_documents({"class_id": c["_id"]})
    return d

@router.post("")
async def create_class(body: ClassIn, lec=Depends(current_lecturer)):
    doc = {"lecturer_id": lec["_id"], "course_code": body.course_code.strip().upper(),
           "course_title": body.course_title.strip(), "description": body.description,
           "enrol_token": new_token(), "enrolment_open": True, "archived": False,
           "created_at": datetime.utcnow()}
    res = await db.classes.insert_one(doc)
    doc["_id"] = res.inserted_id
    return await class_out(doc)

@router.get("")
async def list_classes(archived: bool = False, lec=Depends(current_lecturer)):
    cur = db.classes.find({"lecturer_id": lec["_id"], "archived": archived}).sort("created_at", -1)
    return [await class_out(c) async for c in cur]

@router.get("/overview")
async def overview(lec=Depends(current_lecturer)):
    classes = [c async for c in db.classes.find({"lecturer_id": lec["_id"], "archived": False})]
    cids = [c["_id"] for c in classes]
    sessions = [s async for s in db.attendance_sessions.find({"lecturer_id": lec["_id"]}).sort("start_time", -1)]
    sids = [s["_id"] for s in sessions]
    names = {c["_id"]: f'{c["course_code"]}' for c in classes}
    enrolled = await db.class_enrollments.count_documents({"class_id": {"$in": cids}})
    trend = []
    for s in sessions[:10][::-1]:
        present = await db.attendance_records.count_documents({"session_id": s["_id"]})
        total = await db.class_enrollments.count_documents({"class_id": s["class_id"]})
        trend.append({"label": f'{names.get(s["class_id"], "?")} · {s["start_time"].strftime("%d %b")}',
                      "present": present, "rate": round(100 * present / total) if total else 0})
    recent = []
    async for a in db.attendance_attempts.find({"session_id": {"$in": sids}}).sort("created_at", -1).limit(8):
        recent.append(ser(a))
    active = [{**ser(s), "course_code": names.get(s["class_id"]), "status": session_status(s)}
              for s in sessions if session_status(s) in ("open", "not_started")][:5]
    return {"classes": len(classes), "students": enrolled, "sessions": len(sessions),
            "trend": trend, "recent": recent, "active": active,
            "top_classes": sorted([{"id": str(c["_id"]), "course_code": c["course_code"],
                                    "course_title": c["course_title"],
                                    "sessions": sum(1 for s in sessions if s["class_id"] == c["_id"])} for c in classes],
                                  key=lambda x: -x["sessions"])[:4]}

@router.get("/{class_id}")
async def get_class(class_id: str, lec=Depends(current_lecturer)):
    return await class_out(await owned_class(class_id, lec))

@router.patch("/{class_id}")
async def patch_class(class_id: str, body: ClassPatch, lec=Depends(current_lecturer)):
    c = await owned_class(class_id, lec)
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if "course_code" in upd:
        upd["course_code"] = upd["course_code"].strip().upper()
    if upd:
        await db.classes.update_one({"_id": c["_id"]}, {"$set": upd})
    return await class_out(await db.classes.find_one({"_id": c["_id"]}))

@router.post("/{class_id}/regenerate-link")
async def regen(class_id: str, lec=Depends(current_lecturer)):
    c = await owned_class(class_id, lec)
    await db.classes.update_one({"_id": c["_id"]}, {"$set": {"enrol_token": new_token()}})
    return await class_out(await db.classes.find_one({"_id": c["_id"]}))

@router.get("/{class_id}/students")
async def students(class_id: str, q: str = "", lec=Depends(current_lecturer)):
    c = await owned_class(class_id, lec)
    f = {"class_id": c["_id"]}
    if q:
        f["$or"] = [{"full_name": {"$regex": q, "$options": "i"}}, {"matric_no": {"$regex": q, "$options": "i"}}]
    return [ser(s) async for s in db.class_enrollments.find(f).sort("full_name", 1)]

@router.patch("/{class_id}/students/{enrollment_id}")
async def patch_student(class_id: str, enrollment_id: str, body: StudentPatch, lec=Depends(current_lecturer)):
    c = await owned_class(class_id, lec)
    upd = {k: v.strip() for k, v in body.model_dump().items() if v}
    if "matric_no" in upd:
        upd["matric_no"] = upd["matric_no"].upper()
    await db.class_enrollments.update_one({"_id": oid(enrollment_id), "class_id": c["_id"]}, {"$set": upd})
    await db.audit_logs.insert_one({"lecturer_id": lec["_id"], "action": "student_corrected",
                                    "target": enrollment_id, "changes": upd, "at": datetime.utcnow()})
    return {"ok": True}

@router.delete("/{class_id}/students/{enrollment_id}")
async def remove_student(class_id: str, enrollment_id: str, lec=Depends(current_lecturer)):
    c = await owned_class(class_id, lec)
    e = await db.class_enrollments.find_one({"_id": oid(enrollment_id), "class_id": c["_id"]})
    if e:
        await db.class_enrollments.delete_one({"_id": e["_id"]})
        await db.facial_profiles.delete_many({"enrollment_id": e["_id"]})  # biometric deletion
        await db.audit_logs.insert_one({"lecturer_id": lec["_id"], "action": "student_removed",
                                        "target": e["matric_no"], "at": datetime.utcnow()})
    return {"ok": True}
