from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    MONGO_URL: str = "mongodb://localhost:27017"
    DB_NAME: str = "attendance"
    JWT_SECRET: str = "dev-secret"
    JWT_EXPIRE_MINUTES: int = 60 * 12
    FRONTEND_URL: str = "http://localhost:5173"
    FACE_THRESHOLD: float = 0.40  # cosine similarity (InsightFace buffalo_l)
    MAX_GPS_ACCURACY_M: float = 100
    CLOUDINARY_URL: str = ""
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

settings = Settings()
