from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    data_dir: Path
    db_path: Path
    uploads_dir: Path
    username: str
    password: str
    export_token: str
    host: str
    port: int
    fetch_timeout: float
    max_fetch_bytes: int
    max_upload_bytes: int


def load_settings() -> AppSettings:
    data_dir = Path(os.getenv("RSCFORGE_DATA_DIR", "data")).expanduser().resolve()
    db_path = Path(
        os.getenv("RSCFORGE_DB_PATH", str(data_dir / "rscforge.db"))
    ).expanduser().resolve()
    return AppSettings(
        data_dir=data_dir,
        db_path=db_path,
        uploads_dir=data_dir / "uploads",
        username=os.getenv("RSCFORGE_USERNAME", "admin"),
        password=os.getenv("RSCFORGE_PASSWORD", ""),
        export_token=os.getenv("RSCFORGE_EXPORT_TOKEN", ""),
        host=os.getenv("RSCFORGE_HOST", "0.0.0.0"),
        port=int(os.getenv("RSCFORGE_PORT", "8000")),
        fetch_timeout=float(os.getenv("RSCFORGE_FETCH_TIMEOUT", "30")),
        max_fetch_bytes=int(
            os.getenv("RSCFORGE_MAX_FETCH_BYTES", str(16 * 1024 * 1024))
        ),
        max_upload_bytes=int(
            os.getenv("RSCFORGE_MAX_UPLOAD_BYTES", str(16 * 1024 * 1024))
        ),
    )


settings = load_settings()
