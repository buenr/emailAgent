"""FastAPI entry: run from repo root so `graph_enterprise` package imports resolve."""

from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "graph_enterprise.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
