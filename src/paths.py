"""Resuelve donde viven los datos (CSV/recetario) segun el entorno.

En local, DATA_DIR es simplemente la carpeta data/ del repo. En produccion
(Railway), la variable de entorno DATA_DIR apunta a un Volume persistente
(ej. /data) -- necesario porque el contenedor se reconstruye desde el
repo en cada deploy y perderia cualquier cambio hecho por chat (precios,
ingredientes, produccion diaria) si esos archivos vivieran solo en la imagen.

La primera vez que el volumen esta vacio, se "siembra" copiando los datos del
repo (el catalogo real ya costeado), y de ahi en adelante el volumen manda:
los redeploys nunca vuelven a tocar esos archivos.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

REPO_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_data_dir_env = os.environ.get("DATA_DIR")
DATA_DIR = Path(_data_dir_env) if _data_dir_env else REPO_DATA_DIR


def _seed_data_dir_if_needed() -> None:
    if DATA_DIR == REPO_DATA_DIR:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if (DATA_DIR / "recetas.md").exists():
        return
    for item in REPO_DATA_DIR.iterdir():
        if item.name == "index_recetas":
            continue
        destino = DATA_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, destino, dirs_exist_ok=True)
        else:
            shutil.copy2(item, destino)


_seed_data_dir_if_needed()
