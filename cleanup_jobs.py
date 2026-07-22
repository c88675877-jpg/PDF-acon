#!/usr/bin/env python3
"""Delete old uploaded and generated PDF files."""

from datetime import datetime, timedelta
from pathlib import Path

from backend_config import settings


def cleanup_directory(directory: Path, older_than: datetime) -> int:
    removed = 0
    if not directory.exists():
        return removed

    for path in directory.iterdir():
        if not path.is_file():
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        if modified < older_than:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def main() -> None:
    settings.ensure_dirs()
    older_than = datetime.now() - timedelta(seconds=settings.job_ttl_seconds)
    removed = cleanup_directory(settings.upload_dir, older_than)
    removed += cleanup_directory(settings.output_dir, older_than)
    print(f"Removed {removed} old files.")


if __name__ == "__main__":
    main()
