"""Servidor minimo para exponer el agente en OCI Compute."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agent import build_agent

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Agente Interno Malatesta")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
_executor = None


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


def _get_executor():
    global _executor
    if _executor is None:
        _executor = build_agent()
    return _executor


class Pregunta(BaseModel):
    pregunta: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(body: Pregunta):
    executor = _get_executor()
    resultado = executor.invoke({"input": body.pregunta})
    return {"respuesta": resultado["output"]}
