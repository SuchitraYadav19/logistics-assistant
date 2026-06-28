from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    GOOGLE_API_KEY: str

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    CACHE_TTL_SECONDS: int = 600          # 10 minutes

    # App
    APP_TITLE: str = "Logistics Assistant"
    APP_VERSION: str = "2.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
