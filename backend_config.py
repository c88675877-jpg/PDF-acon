"""Shared backend configuration."""

from dataclasses import dataclass
import os
import tempfile
from pathlib import Path


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.environ.get(name)
    try:
        value = int(raw) if raw is not None else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


@dataclass(frozen=True)
class Settings:
    work_dir: Path
    redis_url: str
    queue_name: str
    max_upload_mb: int
    min_pages: int
    max_pages: int
    default_pages: int
    max_vision_pages: int
    job_timeout_seconds: int
    job_ttl_seconds: int

    @property
    def upload_dir(self) -> Path:
        return self.work_dir / "uploads"

    @property
    def output_dir(self) -> Path:
        return self.work_dir / "outputs"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        work_dir = Path(os.environ.get("PDF_TOC_WORK_DIR", tempfile.gettempdir())) / "pdf_toc_api"
        min_pages = _env_int("MIN_ANALYZE_PAGES", 5, minimum=1)
        max_pages = _env_int("MAX_ANALYZE_PAGES", 100, minimum=min_pages)
        default_pages = _env_int("DEFAULT_ANALYZE_PAGES", 50, minimum=min_pages)
        default_pages = min(default_pages, max_pages)

        return cls(
            work_dir=work_dir,
            redis_url=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
            queue_name=os.environ.get("PDF_TOC_QUEUE", "pdf-toc"),
            max_upload_mb=_env_int("MAX_UPLOAD_MB", 100, minimum=1),
            min_pages=min_pages,
            max_pages=max_pages,
            default_pages=default_pages,
            max_vision_pages=_env_int("MAX_VISION_PAGES", 5, minimum=1),
            job_timeout_seconds=_env_int("JOB_TIMEOUT_SECONDS", 1800, minimum=60),
            job_ttl_seconds=_env_int("JOB_TTL_SECONDS", 7 * 24 * 3600, minimum=3600),
        )

    def ensure_dirs(self) -> None:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)


settings = Settings.from_env()
