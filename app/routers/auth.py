from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError
from ..core.database import db, ser
from ..core.security import hash_password, verify_password, create_token, current_lecturer

router = APIRouter(prefix="/auth", tags=["auth"])

class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

@router.post("/register")
async def register(body: RegisterIn):
    doc = {"full_name": body.full_name.strip(), "email": body.email.lower(),
           "password_hash": hash_password(body.password), "created_at": datetime.utcnow()}
    try:
        res = await db.lecturers.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "An account with this email already exists")
    return {"token": create_token(str(res.inserted_id)), "lecturer": ser({**doc, "_id": res.inserted_id})}

@router.post("/login")
async def login(body: LoginIn):
    lec = await db.lecturers.find_one({"email": body.email.lower()})
    if not lec or not verify_password(body.password, lec["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    return {"token": create_token(str(lec["_id"])), "lecturer": ser(lec)}

@router.get("/me")
async def me(lec=Depends(current_lecturer)):
    return ser(lec)
