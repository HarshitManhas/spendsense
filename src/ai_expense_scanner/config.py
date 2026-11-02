from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_database: str = "spendsense"
    allow_dev_login: bool = False
    google_client_id: str = ""
    frontend_origin: str = "http://localhost:5173"
    model_path: Path = Path("artifacts/best.pt")
    extraction_provider: Literal['checkpoint', 'paddleocr'] = 'checkpoint'
    ocr_python: Path = Path('ocr/.venv/Scripts/python.exe')
    ocr_runner: Path = Path('ocr/run.py')
    ocr_recognition_model_dir: Path | None = None
    remote_worker: bool = False
    ocr_model_id: str = Field(default='', pattern=r'^([a-f0-9]{64})?$')
    vercel: bool = False
    max_upload_mb: int = Field(default=10, ge=1, le=10)
    max_pdf_pages: int = 5

    @model_validator(mode="after")
    def production_guard(self):
        if self.vercel:
            self.app_env = 'production'
            self.max_upload_mb = min(self.max_upload_mb, 4)
            self.remote_worker = True
        if self.app_env != "development":
            if self.allow_dev_login:
                raise ValueError("Development login must be disabled outside development")
            if not self.google_client_id or not self.frontend_origin.startswith("https://"):
                raise ValueError("Production requires Google client ID and an HTTPS origin")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
