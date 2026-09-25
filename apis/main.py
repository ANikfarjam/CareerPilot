"""
REST API for the CareerAI frontend.

Run from the project root:
    uvicorn apis.main:app --reload
Interactive docs at http://localhost:8000/docs
"""

import os

import fastapi
from fastapi.middleware.cors import CORSMiddleware

from apis.reposetories.agents import AGENTS_ROUTER
from apis.reposetories.jobs import JOBS_ROUTER

app = fastapi.FastAPI(title="CareerAI API")

# The Next.js dev server; override with a comma-separated FRONTEND_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("FRONTEND_ORIGINS", "http://localhost:3000").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(AGENTS_ROUTER)
app.include_router(JOBS_ROUTER)


@app.get("/health")
def health():
    """Liveness check for the frontend / docker."""
    return {"status": "ok"}
