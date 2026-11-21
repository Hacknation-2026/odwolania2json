"""API + serwowanie frontendu (GUI)."""

from fastapi import APIRouter, FastAPI, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles

from app.classes.registry import load_classes
from app.config import get_settings
from app.pipeline import process_pdf

app = FastAPI(title="Odwołania2json", version="0.2.0")
api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict:
    return {"status": "ok"}


@api.get("/classes")
def classes() -> dict:
    return {name: c.model_dump() for name, c in load_classes().items()}


@api.post("/extract")
async def extract_endpoint(files: list[UploadFile]) -> list[dict]:
    results = []
    for f in files:
        if not (f.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, f"Nie jest PDF: {f.filename}")
        results.append(await run_in_threadpool(process_pdf, await f.read(), f.filename or ""))
    return results


app.include_router(api)

_frontend = get_settings().frontend_dir
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=_frontend, html=True), name="frontend")
