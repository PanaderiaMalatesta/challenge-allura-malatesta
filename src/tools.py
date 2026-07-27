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
import difflib
import re
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


def _normalizar(texto: str) -> str:
    """Minusculas y sin espacios/guiones bajos, para poder comparar 'masa quebrada'
    contra 'MasaQuebrada_Base' sin que el espaciado o el casing importen."""
    return texto.lower().replace(" ", "").replace("_", "")


def _legible(texto: str) -> str:
    """Convierte identificadores en CamelCase o con guion bajo (ej. 'MurbeNuez',
    'MasaQuebrada_Base') a texto separado por espacios, solo para mostrarlo al
    usuario."""
    texto = texto.replace("_", " ")
    texto = re.sub(r"(?<!^)(?=[A-Z])", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _buscar_filas(catalogo: pd.DataFrame, texto: str) -> pd.DataFrame:
    """Filas cuyo producto+variante+categoria contienen TODAS las palabras de
    `texto` (sin importar mayusculas/espaciado/orden). Tolera que el llamador no
    separe bien producto y variante (ej. pasar "Masa Quebrada Sablee" entero)."""
    palabras = [p for p in re.split(r"\s+", texto.strip().lower()) if p]

    def _coincide(fila) -> bool:
        campo = _normalizar(f"{fila.producto} {fila.variante} {fila.categoria}")
        return all(_normalizar(palabra) in campo for palabra in palabras)

    return catalogo[catalogo.apply(_coincide, axis=1)]


def _alternativas_fuzzy(catalogo: pd.DataFrame, texto: str, minimo: float = 0.35, tope: int = 5) -> list:
    """Filas mas parecidas a `texto` por similitud de texto, para cuando la
    busqueda por palabras no encuentra nada (ej. errores de tipeo)."""
    texto_norm = _normalizar(texto)
    puntajes = [
        (
            difflib.SequenceMatcher(None, texto_norm, _normalizar(f"{fila.producto} {fila.variante}")).ratio(),
            fila,
        )
        for fila in catalogo.itertuples()
    ]
    puntajes.sort(key=lambda par: par[0], reverse=True)
    return [fila for puntaje, fila in puntajes[:tope] if puntaje > minimo]


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
        (ingredientes["producto"].apply(_normalizar) == _normalizar(producto))
        & (ingredientes["variante"].apply(_normalizar) == _normalizar(variante))
    ]
    costos: dict[str, float] = {}
    for fila in filas.itertuples():
        costo = _costo_ingrediente(fila, precios)
        costos[fila.componente] = costos.get(fila.componente, 0.0) + costo
    return costos


def _info_catalogo(producto: str, variante: str) -> pd.Series | None:
    catalogo = _load_catalogo()
    fila = catalogo[
        (catalogo["producto"].apply(_normalizar) == _normalizar(producto))
        & (catalogo["variante"].apply(_normalizar) == _normalizar(variante))
    ]
    if not fila.empty:
        return fila.iloc[0]

    # Coincidencia exacta fallo (ej. el LLM no separo bien producto/variante,
    # como pasar "Masa Quebrada Sablee" completo en el campo producto). Probar
    # de nuevo buscando todas las palabras de ambos campos en conjunto.
    filas = _buscar_filas(catalogo, f"{producto} {variante}")
    return filas.iloc[0] if len(filas) == 1 else None


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
    producto, variante y categoria, sin distinguir mayusculas ni espaciado, palabra
    por palabra). Uso pensado para cuando el usuario pide algo de forma generica
    (ej. "una receta de masa quebrada" o "masa sablee") y hay que preguntarle cual
    variante especifica quiere, en vez de mostrar todo el detalle de costeo de
    una vez."""
    catalogo = _load_catalogo()
    filas = _buscar_filas(catalogo, termino)
    if not filas.empty:
        return "\n".join(f"- {_legible(fila.producto)} {_legible(fila.variante)}" for fila in filas.itertuples())

    # Sin coincidencia exacta/por palabra (ej. errores de tipeo): buscar las
    # alternativas mas parecidas por similitud de texto en vez de fallar.
    mejores = _alternativas_fuzzy(catalogo, termino)
    if not mejores:
        return f"No encontré nada que se parezca a '{termino}'."
    lineas = [f"No encontré una coincidencia exacta con '{termino}'. ¿Quisiste decir alguna de estas?"]
    lineas += [f"- {_legible(fila.producto)} {_legible(fila.variante)}" for fila in mejores]
    return "\n".join(lineas)


def buscar_receta(producto: str) -> str:
    """Devuelve el desglose de componentes y costo unitario de un producto (todas sus
    variantes que coincidan). Acepta texto descriptivo libre (ej. 'masa quebrada
    sablee', 'medialuna'), no hace falta el nombre exacto del producto."""
    catalogo = _load_catalogo()
    filas = _buscar_filas(catalogo, producto)
    if filas.empty:
        mejores = _alternativas_fuzzy(catalogo, producto)
        if mejores:
            opciones = ", ".join(f"{_legible(f.producto)} {_legible(f.variante)}" for f in mejores)
            return f"No encontré '{producto}' exacto. ¿Quisiste decir alguna de estas?: {opciones}"
        disponibles = sorted(catalogo["producto"].unique())
        return f"No encontré '{producto}' en el catálogo. Productos disponibles: {', '.join(disponibles)}."

    lineas = []
    for fila in filas.itertuples():
        if pd.notna(fila.costo_fijo):
            costo_unitario = float(fila.costo_fijo)
            detalle = "costo fijo (sin desglose de insumos)"
        else:
            componentes = _costeo_por_componente(fila.producto, fila.variante)
            costo_unitario = sum(componentes.values())
            detalle = ", ".join(f"{c}: ${v:.0f}" for c, v in componentes.items())
        tiene_precio = pd.notna(fila.precio_venta)
        food_cost = costo_unitario / fila.precio_venta * 100 if tiene_precio else None
        fc_txt = f"{food_cost:.1f}%" if food_cost is not None else "s/precio"
        precio_txt = f"${fila.precio_venta:.0f}" if tiene_precio else "sin precio definido"
        lineas.append(
            f"- {_legible(fila.producto)} {_legible(fila.variante)} [{_legible(fila.categoria)}]: "
            f"costo unitario ${costo_unitario:.0f} ({detalle}) | precio venta {precio_txt} | food cost {fc_txt}"
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
        candidatas = _buscar_filas(catalogo, f"{producto} {variante}")
        if len(candidatas) > 1:
            opciones = ", ".join(f"{_legible(f.producto)} {_legible(f.variante)}" for f in candidatas.itertuples())
            return f"Encontré varias coincidencias para '{producto} {variante}', ¿cuál de estas es?: {opciones}"
        mejores = _alternativas_fuzzy(catalogo, f"{producto} {variante}")
        if mejores:
            opciones = ", ".join(f"{_legible(f.producto)} {_legible(f.variante)}" for f in mejores)
            return f"No encontré '{producto} {variante}' exacto. ¿Quisiste decir alguna de estas?: {opciones}"
        return f"No encontré el producto '{producto}' {variante}."

    producto, variante = info["producto"], info["variante"]
    costo_unitario = costo_unitario_producto(producto, variante)
    precio_unitario_actual = info["precio_venta"]
    tiene_precio = pd.notna(precio_unitario_actual)
    categoria = info["categoria"]

    costo_total = costo_unitario * cantidad

    resultado = [
        f"{_legible(producto)} {_legible(variante)} x{cantidad:g} unidades:",
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
    producto, variante = info["producto"], info["variante"]
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
