"""Optional: retain registration photo privately. Skipped when CLOUDINARY_API_KEY is unset."""
from ..core.config import settings

def upload_private(data_url: str, public_id: str):
    if not settings.CLOUDINARY_API_KEY:
        return None
    import cloudinary, cloudinary.uploader
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )
    r = cloudinary.uploader.upload(data_url, public_id=public_id, type="private", folder="attendance/registrations")
    return r.get("public_id")
