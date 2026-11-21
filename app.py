from __future__ import annotations

import uvicorn

from rscforge.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "rscforge.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
