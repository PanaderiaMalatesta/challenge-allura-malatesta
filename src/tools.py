"""Herramientas deterministicas de costeo e inventario para el agente Malatesta.

Toda la matematica (escalado, sumas, food cost) se hace en Python con los CSV
de datos -- el LLM nunca calcula numeros, solo interpreta la pregunta y llama
a estas funciones. Esto evita que el agente "invente" cifras.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COSTEO_PATH = DATA_DIR / "costeo_unitario.csv"
PRODUCCION_PATH = DATA_DIR / "produccion_diaria.csv"

BENCHMARK_FOOD_COST = {
    "Facturas": (0, 20),
    "Medialuna_Tradicional": (20, 28),
    "Medialuna_Clasica": (24, 30),
    "Medialuna_Especial": (30, 42),
    "Medialuna_Premium": (30, 42),
    "Sandwich": (35, 40),
    "Muffin": (25, 30),
    "Cafe": (25, 35),
}


def _load_costeo() -> pd.DataFrame:
    return pd.read_csv(COSTEO_PATH)


def _load_produccion() -> pd.DataFrame:
    return pd.read_csv(PRODUCCION_PATH)


def _variantes_disponibles(costeo: pd.DataFrame, producto: str) -> pd.DataFrame:
    return costeo[costeo["producto"].str.lower() == producto.lower()]


def buscar_receta(producto: str) -> str:
    """Devuelve el desglose de componentes y costo unitario de un producto (todas sus variantes)."""
    costeo = _load_costeo()
    filas = _variantes_disponibles(costeo, producto)
    if filas.empty:
        disponibles = sorted(costeo["producto"].unique())
        return f"No encontré '{producto}' en el costeo. Productos disponibles: {', '.join(disponibles)}."

    lineas = []
    for variante, grupo in filas.groupby("variante"):
        costo_total = grupo["costo_unitario"].sum()
        precio = grupo["precio_venta"].iloc[0]
        categoria = grupo["categoria"].iloc[0]
        componentes = ", ".join(
            f"{row.componente}: ${row.costo_unitario:.0f}" for row in grupo.itertuples()
        )
        food_cost = costo_total / precio * 100 if precio else None
        fc_txt = f"{food_cost:.1f}%" if food_cost is not None else "s/precio"
        lineas.append(
            f"- {producto} {variante} [{categoria}]: costo unitario ${costo_total:.0f} "
            f"({componentes}) | precio venta ${precio:.0f} | food cost {fc_txt}"
        )
    return "\n".join(lineas)


def escalar_receta(producto: str, variante: str, cantidad: float, food_cost_objetivo: float | None = None) -> str:
    """Escala el costo de un producto/variante para una cantidad objetivo de unidades.

    Si food_cost_objetivo (0-100) se entrega, calcula el precio de venta sugerido
    para lograr ese food cost. Si no, usa el precio de venta ya vigente del catalogo
    (si existe) y muestra el food cost real resultante.
    """
    costeo = _load_costeo()
    filas = costeo[
        (costeo["producto"].str.lower() == producto.lower())
        & (costeo["variante"].str.lower() == variante.lower())
    ]
    if filas.empty:
        disponibles = _variantes_disponibles(costeo, producto)["variante"].unique()
        if len(disponibles) == 0:
            return f"No encontré el producto '{producto}'."
        return f"No encontré la variante '{variante}' de {producto}. Variantes disponibles: {', '.join(disponibles)}."

    costo_unitario = filas["costo_unitario"].sum()
    precio_unitario_actual = filas["precio_venta"].iloc[0]
    categoria = filas["categoria"].iloc[0]

    costo_total = costo_unitario * cantidad

    resultado = [
        f"{producto} {variante} x{cantidad:g} unidades:",
        f"  Costo unitario: ${costo_unitario:.0f} -> Costo total: ${costo_total:.0f}",
    ]

    if food_cost_objetivo is not None:
        precio_sugerido_unitario = costo_unitario / (food_cost_objetivo / 100)
        precio_sugerido_total = precio_sugerido_unitario * cantidad
        resultado.append(
            f"  Precio de venta sugerido para food cost {food_cost_objetivo:.0f}%: "
            f"${precio_sugerido_unitario:.0f}/u -> ${precio_sugerido_total:.0f} total"
        )
    else:
        ingreso_total = precio_unitario_actual * cantidad
        food_cost_real = costo_unitario / precio_unitario_actual * 100 if precio_unitario_actual else None
        ganancia_total = ingreso_total - costo_total
        rango = BENCHMARK_FOOD_COST.get(categoria)
        rango_txt = f" (rango sano de referencia: {rango[0]}-{rango[1]}%)" if rango else ""
        resultado.append(
            f"  Precio de venta actual: ${precio_unitario_actual:.0f}/u -> Ingreso total: ${ingreso_total:.0f}"
        )
        resultado.append(
            f"  Food cost real: {food_cost_real:.1f}%{rango_txt} | Ganancia total: ${ganancia_total:.0f}"
        )

    return "\n".join(resultado)


def registrar_produccion(fecha: str, producto: str, variante: str, cantidad: float) -> str:
    """Registra la produccion del dia (unidades hechas) y calcula el costo/ingreso derivado.

    fecha en formato YYYY-MM-DD. El consumo de materia prima se deriva automaticamente
    del costeo de la receta -- no hace falta anotar insumo por insumo.
    """
    try:
        _dt.date.fromisoformat(fecha)
    except ValueError:
        return "Fecha invalida, usa formato YYYY-MM-DD."

    costeo = _load_costeo()
    filas = costeo[
        (costeo["producto"].str.lower() == producto.lower())
        & (costeo["variante"].str.lower() == variante.lower())
    ]
    if filas.empty:
        return f"No encontré la receta de {producto} {variante}, no se registró producción."

    costo_unitario = filas["costo_unitario"].sum()
    precio_unitario = filas["precio_venta"].iloc[0]
    costo_total = costo_unitario * cantidad
    ingreso_total = precio_unitario * cantidad
    ganancia_total = ingreso_total - costo_total

    nueva_fila = pd.DataFrame([{
        "fecha": fecha,
        "producto": producto,
        "variante": variante,
        "cantidad": cantidad,
        "costo_unitario": costo_unitario,
        "precio_venta_unitario": precio_unitario,
        "costo_total": costo_total,
        "ingreso_total": ingreso_total,
        "ganancia_total": ganancia_total,
    }])

    produccion = _load_produccion()
    produccion = pd.concat([produccion, nueva_fila], ignore_index=True)
    produccion.to_csv(PRODUCCION_PATH, index=False)

    return (
        f"Registrado: {fecha} - {producto} {variante} x{cantidad:g}u. "
        f"Costo insumos: ${costo_total:.0f} | Ingreso: ${ingreso_total:.0f} | Ganancia: ${ganancia_total:.0f}"
    )


def costo_diario(fecha: str) -> str:
    """Suma el costo de produccion, ingreso y ganancia de un dia, desglosado por producto."""
    produccion = _load_produccion()
    del_dia = produccion[produccion["fecha"] == fecha]
    if del_dia.empty:
        return f"No hay producción registrada para {fecha}."

    lineas = [f"Producción del {fecha}:"]
    for (producto, variante), grupo in del_dia.groupby(["producto", "variante"]):
        lineas.append(
            f"  - {producto} {variante}: {grupo['cantidad'].sum():g}u | "
            f"costo ${grupo['costo_total'].sum():.0f} | ingreso ${grupo['ingreso_total'].sum():.0f}"
        )

    costo_total = del_dia["costo_total"].sum()
    ingreso_total = del_dia["ingreso_total"].sum()
    ganancia_total = del_dia["ganancia_total"].sum()
    lineas.append(
        f"TOTAL {fecha}: costo insumos ${costo_total:.0f} | ingreso ${ingreso_total:.0f} | ganancia ${ganancia_total:.0f}"
    )
    return "\n".join(lineas)
