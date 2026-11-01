"""Configuration. Every value can be overridden by an environment variable with the NEWSPAPER_ prefix.

    NEWSPAPER_MAX_UPLOAD_MB=100          allow bigger uploads
    NEWSPAPER_MAX_CONCURRENT_JOBS=2      allow two PDFs to be processed at the same time
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEWSPAPER_")

    max_upload_mb: int = 50
    # OCR is heavy (CPU and RAM). On an 8 GB laptop one job at a time is the safe default.
    max_concurrent_jobs: int = 1
