"""Construye el indice de busqueda semantica sobre el recetario (data/recetas.md).

Se usa para que el agente pueda responder preguntas abiertas sobre como se hace
un producto (ingredientes, procedimiento), separado del costeo numerico exacto
que vive en tools.py / costeo_unitario.csv.
"""
from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import MarkdownTextSplitter

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECETAS_PATH = DATA_DIR / "recetas.md"
INDEX_DIR = DATA_DIR / "index_recetas"


def build_index() -> FAISS:
    loader = TextLoader(str(RECETAS_PATH), encoding="utf-8")
    documentos = loader.load()

    splitter = MarkdownTextSplitter(chunk_size=800, chunk_overlap=100)
    chunks = splitter.split_documents(documentos)

    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    vectorstore = FAISS.from_documents(chunks, embeddings)
    vectorstore.save_local(str(INDEX_DIR))
    return vectorstore


def load_index() -> FAISS:
    embeddings = GoogleGenerativeAIEmbeddings(model="models/text-embedding-004")
    return FAISS.load_local(str(INDEX_DIR), embeddings, allow_dangerous_deserialization=True)


if __name__ == "__main__":
    build_index()
    print(f"Indice creado en {INDEX_DIR}")
