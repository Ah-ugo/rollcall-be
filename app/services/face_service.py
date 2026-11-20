"""Facial registration + one-to-one verification (OpenCV + InsightFace)."""
import base64, os, numpy as np, cv2
from fastapi import HTTPException

_app = None

def _model():
    global _app
    if _app is None:
        from insightface.app import FaceAnalysis
        _app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=-1, det_size=(640, 640))
    return _app

def decode_image(data_url: str):
    try:
        raw = base64.b64decode(data_url.split(",")[-1])
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        assert img is not None
        return img
    except Exception:
        raise HTTPException(400, "Invalid image")

def embed(data_url: str) -> np.ndarray:
    img = decode_image(data_url)
    h, w = img.shape[:2]
    if min(h, w) < 200:
        raise HTTPException(422, "Image resolution too low. Move to better light and retry.")
    if cv2.Laplacian(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() < float(os.getenv("FACE_BLUR_THRESHOLD", "10")):
        raise HTTPException(422, "Image is blurry. Hold the device steady and retry.")
    faces = _model().get(img)
    if not faces:
        raise HTTPException(422, "No face detected. Face the camera in good light.")
    if len(faces) > 1:
        raise HTTPException(422, "More than one face detected. Only the student should be in frame.")
    f = faces[0]
    x1, y1, x2, y2 = f.bbox
    if (x2 - x1) < 0.18 * w:
        raise HTTPException(422, "Face is too small or far away. Move closer.")
    return f.normed_embedding.astype(np.float32)

def similarity(a, b) -> float:
    a, b = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
