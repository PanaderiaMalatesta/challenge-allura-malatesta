"""Herramientas deterministicas de costeo e inventario para el agente Malatesta.

Toda la matematica (escalado, sumas, food cost) se hace en Python con los CSV
de datos -- el LLM nunca calcula numeros, solo interpreta la pregunta y llama
a estas funciones. Esto evita que el agente "invente" cifras.

El costo de cada producto se calcula EN VIVO a partir de sus insumos
(recetas_ingredientes.csv x precios_insumos.csv), asi que si se actualiza el
precio de un insumo, todos los productos que lo usan quedan recosteados
automaticamente sin tocar ningun otro archivo.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INGREDIENTES_PATH = DATA_DIR / "recetas_ingredientes.csv"
PRECIOS_INSUMOS_PATH = DATA_DIR / "precios_insumos.csv"
CATALOGO_PATH = DATA_DIR / "catalogo_precios.csv"
PRODUCCION_PATH = DATA_DIR / "produccion_diaria.csv"

# Factor para convertir la unidad de la receta a la unidad en que esta
# cotizado el insumo (que siempre es kg, L, unidad o porcion).
_FACTOR_A_UNIDAD_INSUMO = {
    "g": ("kg", 0.001),
    "mL": ("L", 0.001),
    "kg": ("kg", 1),
    "L": ("L", 1),
    "unidad": ("unidad", 1),
    "porcion": ("porcion", 1),
}

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


def _read_csv_flexible(path: Path) -> pd.DataFrame:
    """Lee un CSV detectando automaticamente si el delimitador es ',' o ';'.

    Excel en configuracion regional de Chile guarda "CSV separado por comas"
    usando ';' como delimitador real, asi que hay que tolerar ambos casos
    para que editar los datos en Excel no rompa la lectura.
    """
    return pd.read_csv(path, sep=None, engine="python")


def _load_precios_insumos() -> pd.DataFrame:
    return _read_csv_flexible(PRECIOS_INSUMOS_PATH)


def _load_ingredientes() -> pd.DataFrame:
    return _read_csv_flexible(INGREDIENTES_PATH)


def _load_catalogo() -> pd.DataFrame:
    return _read_csv_flexible(CATALOGO_PATH)


def _load_produccion() -> pd.DataFrame:
    return _read_csv_flexible(PRODUCCION_PATH)


def _costo_ingrediente(fila, precios: pd.DataFrame) -> float:
    match = precios[precios["insumo"].str.lower() == fila.insumo.lower()]
    if match.empty:
        raise ValueError(f"Insumo '{fila.insumo}' no tiene precio registrado en precios_insumos.csv")
    unidad_insumo_esperada, factor = _FACTOR_A_UNIDAD_INSUMO[fila.unidad]
    precio_por_unidad = match.iloc[0]["precio"]
    return fila.cantidad * factor * precio_por_unidad


def _costeo_por_componente(producto: str, variante: str) -> dict[str, float]:
    """Devuelve el costo de cada componente (Masa, Relleno, ...) para una variante, calculado en vivo."""
    ingredientes = _load_ingredientes()
    precios = _load_precios_insumos()
    filas = ingredientes[
        (ingredientes["producto"].str.lower() == producto.lower())
        & (ingredientes["variante"].str.lower() == variante.lower())
    ]
    costos: dict[str, float] = {}
    for fila in filas.itertuples():
        costo = _costo_ingrediente(fila, precios)
        costos[fila.componente] = costos.get(fila.componente, 0.0) + costo
    return costos


def _info_catalogo(producto: str, variante: str) -> pd.Series | None:
    catalogo = _load_catalogo()
    fila = catalogo[
        (catalogo["producto"].str.lower() == producto.lower())
        & (catalogo["variante"].str.lower() == variante.lower())
    ]
    return None if fila.empty else fila.iloc[0]


def costo_unitario_producto(producto: str, variante: str) -> float:
    """Costo unitario total de un producto/variante, calculado en vivo desde insumos.

    Si el producto tiene `costo_fijo` en el catalogo (ej. recetas sin desglose de
    insumos, como el Muffin), se usa ese valor en vez de calcular desde ingredientes.
    """
    info = _info_catalogo(producto, variante)
    if info is not None and pd.notna(info.get("costo_fijo")):
        return float(info["costo_fijo"])
    return sum(_costeo_por_componente(producto, variante).values())


def listar_precios_insumos(filtro: str | None = None) -> str:
    """Lista el precio vigente de las materias primas. Si se da `filtro`, solo
    muestra los insumos cuyo nombre lo contenga (busqueda parcial, sin distinguir mayusculas)."""
    precios = _load_precios_insumos()
    if filtro:
        precios = precios[precios["insumo"].str.contains(filtro, case=False)]
    if precios.empty:
        return f"No encontré insumos que coincidan con '{filtro}'."
    lineas = [f"- {fila.insumo}: ${fila.precio:.0f}/{fila.unidad}" for fila in precios.itertuples()]
    return "\n".join(lineas)


def actualizar_precio_insumo(insumo: str, nuevo_precio: float) -> str:
    """Actualiza el precio de un insumo (materia prima). Todos los productos que lo usan
    quedan recosteados automaticamente la próxima vez que se consulten."""
    precios = _load_precios_insumos()
    mask = precios["insumo"].str.lower() == insumo.lower()
    if not mask.any():
        disponibles = sorted(precios["insumo"].unique())
        return f"No encontré el insumo '{insumo}'. Insumos disponibles: {', '.join(disponibles)}."

    precio_anterior = precios.loc[mask, "precio"].iloc[0]
    precios.loc[mask, "precio"] = nuevo_precio
    precios.to_csv(PRECIOS_INSUMOS_PATH, index=False)

    nombre_real = precios.loc[mask, "insumo"].iloc[0]
    return f"Precio de {nombre_real} actualizado: ${precio_anterior:.0f} -> ${nuevo_precio:.0f}."


def listar_variantes(termino: str) -> str:
    """Lista los nombres de producto/variante que coincidan con `termino` (busca en
    producto y categoria, sin distinguir mayusculas). Uso pensado para cuando el
    usuario pide algo de forma generica (ej. "una receta de masa quebrada") y hay
    que preguntarle cual variante especifica quiere, en vez de mostrar todo el
    detalle de costeo de una vez."""
    catalogo = _load_catalogo()
    mask = catalogo["producto"].str.contains(termino, case=False) | catalogo["categoria"].str.contains(
        termino, case=False
    )
    filas = catalogo[mask]
    if filas.empty:
        return f"No encontré nada que coincida con '{termino}'."
    return "\n".join(f"- {fila.producto} {fila.variante}" for fila in filas.itertuples())


def buscar_receta(producto: str) -> str:
    """Devuelve el desglose de componentes y costo unitario de un producto (todas sus variantes)."""
    catalogo = _load_catalogo()
    filas = catalogo[catalogo["producto"].str.lower() == producto.lower()]
    if filas.empty:
        disponibles = sorted(catalogo["producto"].unique())
        return f"No encontré '{producto}' en el catálogo. Productos disponibles: {', '.join(disponibles)}."

    lineas = []
    for fila in filas.itertuples():
        if pd.notna(fila.costo_fijo):
            costo_unitario = float(fila.costo_fijo)
            detalle = "costo fijo (sin desglose de insumos)"
        else:
            componentes = _costeo_por_componente(producto, fila.variante)
            costo_unitario = sum(componentes.values())
            detalle = ", ".join(f"{c}: ${v:.0f}" for c, v in componentes.items())
        tiene_precio = pd.notna(fila.precio_venta)
        food_cost = costo_unitario / fila.precio_venta * 100 if tiene_precio else None
        fc_txt = f"{food_cost:.1f}%" if food_cost is not None else "s/precio"
        precio_txt = f"${fila.precio_venta:.0f}" if tiene_precio else "sin precio definido"
        lineas.append(
            f"- {producto} {fila.variante} [{fila.categoria}]: costo unitario ${costo_unitario:.0f} "
            f"({detalle}) | precio venta {precio_txt} | food cost {fc_txt}"
        )
    return "\n".join(lineas)


def escalar_receta(producto: str, variante: str, cantidad: float, food_cost_objetivo: float | None = None) -> str:
    """Escala el costo de un producto/variante para una cantidad objetivo de unidades.

    Si food_cost_objetivo (0-100) se entrega, calcula el precio de venta sugerido
    para lograr ese food cost. Si no, usa el precio de venta ya vigente del catalogo
    (si existe) y muestra el food cost real resultante.
    """
    info = _info_catalogo(producto, variante)
    if info is None:
        catalogo = _load_catalogo()
        disponibles = catalogo[catalogo["producto"].str.lower() == producto.lower()]["variante"].unique()
        if len(disponibles) == 0:
            return f"No encontré el producto '{producto}'."
        return f"No encontré la variante '{variante}' de {producto}. Variantes disponibles: {', '.join(disponibles)}."

    costo_unitario = costo_unitario_producto(producto, variante)
    precio_unitario_actual = info["precio_venta"]
    tiene_precio = pd.notna(precio_unitario_actual)
    categoria = info["categoria"]

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
    elif not tiene_precio:
        resultado.append("  Este producto todavía no tiene precio de venta definido en el catálogo.")
    else:
        ingreso_total = precio_unitario_actual * cantidad
        food_cost_real = costo_unitario / precio_unitario_actual * 100
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

    info = _info_catalogo(producto, variante)
    if info is None:
        return f"No encontré la receta de {producto} {variante}, no se registró producción."
    if pd.isna(info["precio_venta"]):
        return f"{producto} {variante} todavía no tiene precio de venta definido, no se puede registrar producción."

    costo_unitario = costo_unitario_producto(producto, variante)
    precio_unitario = info["precio_venta"]
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
