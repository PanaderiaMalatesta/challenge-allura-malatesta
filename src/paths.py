"""Resuelve donde viven los datos (CSV/recetario) segun el entorno, y los
mantiene sincronizados entre el repo y el volumen persistente en cada deploy.

En local, DATA_DIR es simplemente la carpeta data/ del repo. En produccion
(Railway), la variable de entorno DATA_DIR apunta a un Volume persistente
(ej. /data) -- necesario porque el contenedor se reconstruye desde el
repo en cada deploy y perderia cualquier cambio hecho por chat (precios,
ingredientes, produccion diaria) si esos archivos vivieran solo en la imagen.

La primera vez que el volumen esta vacio, se "siembra" copiando todos los
datos del repo tal cual.

De ahi en adelante, cada archivo se sincroniza segun si el chat puede
modificarlo o no:
- recetas.md NUNCA se edita por chat (no existe ninguna herramienta para
  eso, solo se toca por git) -- se sincroniza completo del repo en cada
  deploy, para que agregar una receta nueva y hacer push sea suficiente,
  sin tener que entrar por SSH a copiarla a mano al volumen.
- Los CSV de costeo (catalogo_precios.csv, recetas_ingredientes.csv,
  precios_insumos.csv) SI se editan por chat (precios, ingredientes nuevos,
  etc.) -- nunca se sobreescriben. Se fusionan de forma ADITIVA: las filas
  nuevas que aparecen en el repo (ej. una receta nueva agregada por git) se
  agregan al volumen, pero cualquier fila que ya exista en el volumen se
  deja intacta, para no perder ediciones hechas en produccion por chat.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pandas as pd

REPO_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_data_dir_env = os.environ.get("DATA_DIR")
DATA_DIR = Path(_data_dir_env) if _data_dir_env else REPO_DATA_DIR

# nombre del CSV -> columnas que identifican una fila de forma unica, para
# saber si una fila del repo ya existe en el volumen o es nueva.
_CSVS_ADITIVOS = {
    "catalogo_precios.csv": ["producto", "variante"],
    "recetas_ingredientes.csv": ["producto", "variante", "componente", "insumo"],
    "precios_insumos.csv": ["insumo"],
}

# Archivos que nunca se editan por chat -- siempre se sincronizan enteros
# del repo al volumen (el repo manda, sin fusion).
_ARCHIVOS_SIEMPRE_DEL_REPO = ["recetas.md"]


def _fusionar_csv_aditivo(nombre: str, columnas_clave: list[str]) -> None:
    """Agrega al CSV del volumen las filas del CSV del repo que no existan
    todavia (por columnas_clave), sin tocar ni borrar ninguna fila que ya
    este en el volumen."""
    origen = REPO_DATA_DIR / nombre
    destino = DATA_DIR / nombre
    if not origen.exists():
        return
    if not destino.exists():
        shutil.copy2(origen, destino)
        return

    df_repo = pd.read_csv(origen, sep=None, engine="python")
    df_volumen = pd.read_csv(destino, sep=None, engine="python")

    claves_existentes = set(map(tuple, df_volumen[columnas_clave].astype(str).values))
    es_nueva = ~df_repo[columnas_clave].astype(str).apply(tuple, axis=1).isin(claves_existentes)
    filas_nuevas = df_repo[es_nueva]
    if filas_nuevas.empty:
        return

    df_combinado = pd.concat([df_volumen, filas_nuevas], ignore_index=True)
    df_combinado.to_csv(destino, index=False)


def _sincronizar_data_dir() -> None:
    if DATA_DIR == REPO_DATA_DIR:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not (DATA_DIR / "recetas.md").exists():
        # Volumen vacio: primera siembra completa, copiar todo tal cual.
        for item in REPO_DATA_DIR.iterdir():
            if item.name == "index_recetas":
                continue
            destino = DATA_DIR / item.name
            if item.is_dir():
                shutil.copytree(item, destino, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destino)
        return

    for nombre in _ARCHIVOS_SIEMPRE_DEL_REPO:
        origen = REPO_DATA_DIR / nombre
        if origen.exists():
            shutil.copy2(origen, DATA_DIR / nombre)

    for nombre, columnas_clave in _CSVS_ADITIVOS.items():
        _fusionar_csv_aditivo(nombre, columnas_clave)


_sincronizar_data_dir()
