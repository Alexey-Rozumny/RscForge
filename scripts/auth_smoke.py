"""Smoke test for Basic auth and the export token."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

data_dir = Path(tempfile.mkdtemp(prefix="rscforge-auth-smoke-"))
os.environ["RSCFORGE_DATA_DIR"] = str(data_dir)
os.environ["RSCFORGE_USERNAME"] = "admin"
os.environ["RSCFORGE_PASSWORD"] = "secret"
os.environ["RSCFORGE_EXPORT_TOKEN"] = "token-123"

from fastapi.testclient import TestClient  # noqa: E402

from rscforge.main import app  # noqa: E402


def main() -> None:
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/").status_code == 401
        assert client.get("/").headers["www-authenticate"].startswith("Basic")

        authorized = client.get("/", auth=("admin", "secret"))
        assert authorized.status_code == 200, authorized.text
        assert client.get("/", auth=("admin", "wrong")).status_code == 401

        assert client.get("/export.rsc").status_code == 401
        assert client.get("/export.rsc?token=wrong").status_code == 401
        assert client.get("/export.rsc?token=token-123").status_code == 200

    print(f"auth smoke ok ({data_dir})")


if __name__ == "__main__":
    main()
