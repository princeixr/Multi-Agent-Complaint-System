"""ASGI entry point for the complaint-processing API."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.db.session import init_db
from app.observability.logging import setup_logging
from app.observability.tracing import setup_tracing


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_logging()
    setup_tracing()
    init_db()
    yield


app = FastAPI(
    title="Complaint classification agent",
    description="LangGraph pipeline for consumer complaint intake, classification, risk, and resolution.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/", include_in_schema=False)
async def root() -> dict:
    return {"service": "complaint-classification", "docs": "/docs"}

