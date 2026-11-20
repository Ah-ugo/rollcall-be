import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import db
from app.core.security import hash_password


async def seed(full_name: str, email: str, password: str):
    existing = await db.lecturers.find_one({"email": email.lower()})
    if existing:
        print(f"Lecturer already exists: {email} (id={existing['_id']})")
        return str(existing["_id"])
    doc = {
        "full_name": full_name.strip(),
        "email": email.lower(),
        "password_hash": hash_password(password),
        "created_at": __import__("datetime").datetime.utcnow(),
    }
    res = await db.lecturers.insert_one(doc)
    print(f"Seeded lecturer: {email} (id={res.inserted_id})")
    return str(res.inserted_id)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "Lecturer One"
    email = sys.argv[2] if len(sys.argv) > 2 else "lecturer@example.com"
    password = sys.argv[3] if len(sys.argv) > 3 else "Lecturer@1234"
    asyncio.run(seed(name, email, password))
