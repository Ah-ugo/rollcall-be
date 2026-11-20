# Rollcall Backend

FastAPI + MongoDB backend for Rollcall — QR + face + location attendance.

## Stack
- FastAPI, uvicorn — ASGI web server
- Motor + MongoDB — async document store
- InsightFace (buffalo_l) + OpenCV + onnxruntime — 1:1 face verification
- PyJWT + bcrypt — auth & password hashing
- qrcode — QR generation
- Cloudinary (optional) — private registration photo storage

## Setup
```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set JWT_SECRET, MONGO_URL, and optional Cloudinary creds
uvicorn app.main:app --reload --port 8000
```
InsightFace downloads the `buffalo_l` model (~280 MB) on first face request.

## Environment variables
| Variable | Purpose |
|---|---|
| `MONGO_URL` | MongoDB connection string |
| `DB_NAME` | Database name |
| `JWT_SECRET` | Signing secret for session tokens |
| `JWT_EXPIRE_MINUTES` | Token expiry (default 720) |
| `FRONTEND_URL` | Frontend origin for attendance links |
| `FACE_THRESHOLD` | Cosine similarity threshold (default 0.40) |
| `MAX_GPS_ACCURACY_M` | Max acceptable GPS accuracy in metres (default 100) |
| `FACE_BLUR_THRESHOLD` | Laplacian variance blur floor (default 10) |
| `CLOUDINARY_CLOUD_NAME` / `CLOUDINARY_API_KEY` / `CLOUDINARY_API_SECRET` | Optional Cloudinary credentials |

## Endpoints
- `POST /auth/register` — register a lecturer
- `POST /auth/login` — login, returns JWT
- `GET /auth/me` — current lecturer (requires token)
- `POST /classes` / `GET /classes` — manage classes
- `POST /classes/{id}/sessions` — create an attendance session
- `POST /public/enrol/{token}` — student face enrolment
- `POST /public/attend/{token}/verify` — student attendance verify (face + GPS)
- `WS /ws/sessions/{id}` — real-time attendance updates for lecturer

## Notes
Liveness is a two-frame challenge, not certified anti-spoofing. GPS can be spoofed or drift indoors. Deploy over HTTPS, obtain student consent, and set a retention policy.
