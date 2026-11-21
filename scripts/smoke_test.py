"""End-to-end smoke test against an isolated temporary data directory."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

data_dir = Path(tempfile.mkdtemp(prefix="rscforge-smoke-"))
os.environ["RSCFORGE_DATA_DIR"] = str(data_dir)
os.environ.pop("RSCFORGE_PASSWORD", None)
os.environ.pop("RSCFORGE_EXPORT_TOKEN", None)

from fastapi.testclient import TestClient  # noqa: E402

from rscforge import resolver  # noqa: E402
from rscforge.main import app  # noqa: E402

RESOLVED = {
    "example.com": ["203.0.113.10"],
    "ads.example.com": ["203.0.113.11"],
}


async def fake_resolve_domains(domains):
    return {domain: RESOLVED.get(domain, []) for domain in domains}


def main() -> None:
    # Keep the smoke test deterministic: no real DNS lookups.
    resolver.resolve_domains = fake_resolve_domains
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200

        index = client.get("/")
        assert index.status_code == 200
        assert "RscForge" in index.text

        created = client.post(
            "/api/entries",
            json={"value": "example.com\n1.2.3.4/24", "comment": "smoke"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["created"] == 2

        upload = client.post(
            "/api/sources/upload",
            files={"file": ("list.txt", b"0.0.0.0 ads.example.com\n", "text/plain")},
            data={"name": "Smoke source", "refresh_interval_minutes": "60"},
        )
        assert upload.status_code == 201, upload.text
        source = upload.json()
        assert source["entry_count"] == 1, source

        stats = client.get("/api/entries/stats").json()
        assert stats["total"] == 3, stats
        assert stats["domains"] == 2, stats
        assert stats["ip_entries"] == 1, stats

        preview = client.get("/api/export/preview")
        assert preview.status_code == 200
        content = preview.json()["content"]
        assert "address=203.0.113.10" in content
        assert "rscforge:example.com" in content
        assert "address=1.2.3.0/24" in content
        assert "address=203.0.113.11" in content
        assert "comment=\"rscforge:ads.example.com\"" in content

        settings = client.get("/api/settings").json()
        values = settings["values"]
        values.update(include_pbr=True, vpn_gateway="10.8.0.1")
        patched = client.patch("/api/settings", json=values)
        assert patched.status_code == 200, patched.text

        content = client.get("/api/export/preview").json()["content"]
        assert "/ip/firewall/mangle" in content
        assert 'gateway="10.8.0.1"' in content

        export = client.get("/export.rsc")
        assert export.status_code == 200
        assert "address=203.0.113.10" in export.text

        deleted = client.delete(f"/api/sources/{source['id']}")
        assert deleted.status_code == 204
        assert client.get("/api/entries/stats").json()["total"] == 2

    print(f"smoke ok ({data_dir})")


if __name__ == "__main__":
    main()
