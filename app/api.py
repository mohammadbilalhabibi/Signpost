"""FastAPI application. RAG endpoints are added in later steps."""

from fastapi import FastAPI

app = FastAPI(title="Degbot", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
