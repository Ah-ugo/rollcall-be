from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError
from ..core.database import db
from ..services import face_service
from ..services.cloudinary_service import upload_private

router = APIRouter(prefix="/public/enrol", tags=["enrolment"])

class EnrolIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    matric_no: str = Field(min_length=3, max_length=30)
    image: str
    consent: bool

async def _class(token: str):
    c = await db.classes.find_one({"enrol_token": token})
    if not c or c.get("archived"):
        raise HTTPException(404, "This enrolment link is invalid")
    return c

@router.get("/{token}")
async def info(token: str):
    c = await _class(token)
    lec = await db.lecturers.find_one({"_id": c["lecturer_id"]})
    return {"course_code": c["course_code"], "course_title": c["course_title"],
            "lecturer": lec["full_name"] if lec else "", "open": c["enrolment_open"]}

@router.post("/{token}")
async def enrol(token: str, body: EnrolIn):
    c = await _class(token)
    if not c["enrolment_open"]:
        raise HTTPException(403, "Enrolment for this class is closed")
    if not body.consent:
        raise HTTPException(400, "Consent to facial registration is required")
    matric = body.matric_no.strip().upper()
    if await db.class_enrollments.find_one({"class_id": c["_id"], "matric_no": matric}):
        raise HTTPException(409, "This matriculation number is already enrolled in this class")
    emb = face_service.embed(body.image)
    enr = {"class_id": c["_id"], "full_name": body.full_name.strip(), "matric_no": matric,
           "consented_at": datetime.utcnow(), "created_at": datetime.utcnow()}
    try:
        res = await db.class_enrollments.insert_one(enr)
    except DuplicateKeyError:
        raise HTTPException(409, "This matriculation number is already enrolled in this class")
    img_ref = upload_private(body.image, str(res.inserted_id))
    await db.facial_profiles.insert_one({"enrollment_id": res.inserted_id, "embedding": emb.tolist(),
                                         "image_ref": img_ref, "created_at": datetime.utcnow()})
    return {"ok": True, "course_code": c["course_code"], "full_name": enr["full_name"], "matric_no": matric}
