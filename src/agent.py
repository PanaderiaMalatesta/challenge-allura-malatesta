"""Agente interno de administracion Malatesta.

Combina:
- Herramientas deterministicas de costeo/inventario (tools.py) -- toda la
  matematica pasa por Python, nunca por el LLM.
- Un retriever sobre el recetario (ingest.py) para preguntas abiertas sobre
  ingredientes/procedimientos.

Usa la API de agentes de LangChain 1.x (`create_agent`, basada en LangGraph).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.tools import tool
from langchain_cohere import ChatCohere

from . import tools as t
from .ingest import load_index

load_dotenv()

SYSTEM_PROMPT = """Eres el asistente interno de administración de la Panadería
Artesanal Malatesta (Villarrica, Chile). Tu usuario es Raúl (dueño) o el
panadero, NO un cliente final.

Tu trabajo:
1. Responder preguntas sobre recetas e ingredientes (usa la herramienta de
   búsqueda en el recetario).
2. Calcular el costo de fabricación al escalar un pedido a una cantidad
   específica (ej. "50 medialunas de pistacho para un evento") -- útil para
   negociar precios con clientes de pedidos grandes.
3. Registrar la producción diaria y calcular el costo/ganancia del día.
4. Consultar el precio vigente de una o varias materias primas, y actualizarlo
   cuando el usuario lo indique (ej. "la harina subió a $950 el kilo") -- esto
   recostea automáticamente todos los productos que usan ese insumo, no hace
   falta tocar nada más.

Reglas importantes:
- Distingue bien qué está pidiendo el usuario:
  - Si pide LA RECETA (ingredientes, cantidades, procedimiento, "cómo se
    hace", "de qué está hecho") → usa herramienta_buscar_en_recetario, que
    busca en el texto del recetario. NO uses herramienta_buscar_receta para
    esto, esa herramienta es solo de costeo y NO devuelve ingredientes ni
    pasos de preparación. Después de mostrar la receta, SIEMPRE pregunta
    "¿qué cantidad necesitas hacer?" antes de terminar la respuesta. Cuando el
    usuario te responda con la cantidad, usa herramienta_escalar_ingredientes
    (no herramienta_escalar_receta, que da el costo) para darle la lista de
    insumos ya escalada en unidades reales (gramos/kg/L/unidades) para esa
    cantidad.
  - Si pide el COSTO, PRECIO, FOOD COST o GANANCIA → usa
    herramienta_buscar_receta / herramienta_escalar_receta (costeo
    determinístico).
- Si el usuario pide algo (receta o costo) de forma GENÉRICA por categoría o
  producto, sin indicar cuál variante específica (ej. "dame una receta de masa
  quebrada", "cuánto cuesta una medialuna"), NO muestres todas las variantes
  de una vez. En su lugar, usa herramienta_listar_variantes, que devuelve las
  opciones ya numeradas (1., 2., 3., ...) -- muéstraselas al usuario tal cual,
  en una lista numerada, y pregúntale cuál número quiere conocer. Si el
  usuario responde solo con un número (ej. "2" o "la 2"), interpreta que se
  refiere a esa posición de la ÚLTIMA lista numerada que le mostraste, y usa
  el nombre de producto/variante correspondiente a esa posición para llamar a
  la herramienta que corresponda SEGÚN LA INTENCIÓN ORIGINAL del usuario (si
  pidió una receta, ve a buscar_en_recetario con ese nombre; si pidió costo,
  ve a escalar_receta/buscar_receta).
- NUNCA inventes ni calcules cifras de memoria. Todo número de costo, precio o
  food cost debe salir de las herramientas (escalar_receta, buscar_receta,
  registrar_produccion, costo_diario). Si una herramienta no tiene el dato,
  dilo claramente en vez de estimar.
- Si el usuario no especifica la variante de un producto (ej. solo dice
  "medialunas" sin decir cuál sabor), pregunta o usa herramienta_listar_variantes
  para mostrar las variantes disponibles.
- Responde siempre en español, de forma directa y con las cifras en pesos
  chilenos (CLP).
- Si el usuario quiere ajustar la receta ESTÁNDAR de producción dando la
  cantidad real de un solo ingrediente en el LOTE completo que se mezcla en
  cocina (ej. "el pastón de medialunas ahora se hace con 5 kg de harina"),
  usa herramienta_estandarizar_receta_por_ingrediente -- reescala todos los
  demás insumos de ese componente proporcionalmente, no hace falta pedirle el
  rendimiento del lote (el sistema ya lo sabe por receta).
- El usuario puede pedirte modificar una receta directamente por chat:
  agregar un insumo nuevo, quitar uno, cambiar su cantidad, o reemplazarlo por
  otro insumo distinto (ej. "quita la sal de la Factura de Manjar", "agrega
  50g de nueces a la Medialuna Pistacho", "cambia la mantequilla de la Masa
  Sablée a 90 gramos", "reemplaza la margarina por mantequilla en la
  Factura"). Usa herramienta_agregar_ingrediente_receta,
  herramienta_eliminar_ingrediente_receta,
  herramienta_editar_ingrediente_receta o
  herramienta_reemplazar_ingrediente_receta según corresponda. Si un insumo
  aparece en más de un componente de la receta (ej. azúcar en la masa y en el
  almíbar), la herramienta te va a pedir que especifiques cuál -- pregúntale
  al usuario en ese caso, no adivines.
- Eliminar un ingrediente es destructivo: NUNCA llames a
  herramienta_eliminar_ingrediente_receta con confirmado=True directamente.
  Primero llámala con confirmado=False (el default) -- te va a devolver una
  pregunta tipo "¿Confirmas eliminar X de la receta Y?", muéstrasela al
  usuario tal cual y espera su respuesta. Solo si el usuario confirma
  (dice que sí, ok, confirmo, etc.) vuelve a llamar a la herramienta con
  confirmado=True para borrar de verdad. Si el usuario no confirma, no
  elimines nada.
"""


@tool
def herramienta_estandarizar_receta_por_ingrediente(
    producto: str, variante: str, componente: str, insumo_ancla: str, cantidad_lote: float, unidad_lote: str,
) -> str:
    """Redefine la receta ESTANDAR de un componente (ej. la Masa de una
    Medialuna) dando la cantidad real de UN insumo ancla en el lote completo
    que se mezcla en cocina (ej. 'el pastón usa 4,8 kg de harina'). El sistema
    ya sabe cuantas unidades rinde ese lote, calcula el factor de cambio y
    reescala PROPORCIONALMENTE todos los demas insumos de ese componente
    automaticamente -- usar esto cuando el usuario quiera ajustar la receta
    estandar de producción en base a un ingrediente, no gramo por gramo."""
    return t.estandarizar_receta_por_ingrediente(producto, variante, componente, insumo_ancla, cantidad_lote, unidad_lote)


@tool
def herramienta_agregar_ingrediente_receta(producto: str, variante: str, componente: str, insumo: str, cantidad: float, unidad: str) -> str:
    """Agrega un insumo nuevo a una receta (componente ej. 'Masa', 'Relleno',
    'Almibar', 'Cobertura'). Si el producto/variante no existia, se crea.
    unidad debe ser: g, mL, kg, L, unidad o porcion."""
    return t.agregar_ingrediente_receta(producto, variante, componente, insumo, cantidad, unidad)


@tool
def herramienta_eliminar_ingrediente_receta(
    producto: str, variante: str, insumo: str, componente: str | None = None, confirmado: bool = False,
) -> str:
    """Elimina un insumo de una receta. Tolera texto libre/errores de tipeo en el
    nombre del insumo. Si aparece en mas de un componente, pasa `componente`.
    SIEMPRE llamar primero con confirmado=False (el default) -- devuelve una
    pregunta de confirmacion, NO borra nada todavia. Solo pasar confirmado=True
    en una segunda llamada, despues de que el usuario responda que si."""
    return t.eliminar_ingrediente_receta(producto, variante, insumo, componente, confirmado)


@tool
def herramienta_editar_ingrediente_receta(
    producto: str, variante: str, insumo: str, nueva_cantidad: float,
    componente: str | None = None, nueva_unidad: str | None = None,
) -> str:
    """Cambia la cantidad (y opcionalmente la unidad) de un insumo que ya esta en
    una receta. Si aparece en mas de un componente, pasa `componente`."""
    return t.editar_ingrediente_receta(producto, variante, insumo, nueva_cantidad, componente, nueva_unidad)


@tool
def herramienta_reemplazar_ingrediente_receta(
    producto: str, variante: str, insumo_actual: str, insumo_nuevo: str,
    cantidad: float, unidad: str, componente: str | None = None,
) -> str:
    """Reemplaza un insumo de una receta por otro distinto, con nueva cantidad y
    unidad, en el mismo componente."""
    return t.reemplazar_ingrediente_receta(producto, variante, insumo_actual, insumo_nuevo, cantidad, unidad, componente)


@tool
def herramienta_listar_precios_insumos(filtro: str | None = None) -> str:
    """Lista el precio vigente de las materias primas (insumos). Si se da `filtro`,
    solo muestra los que coincidan con ese texto (ej. 'harina')."""
    return t.listar_precios_insumos(filtro)


@tool
def herramienta_actualizar_precio_insumo(insumo: str, nuevo_precio: float) -> str:
    """Actualiza el precio de una materia prima (ej. 'harina_0000', 'mantequilla').
    Todos los productos que usan ese insumo quedan recosteados automáticamente."""
    return t.actualizar_precio_insumo(insumo, nuevo_precio)


@tool
def herramienta_listar_variantes(termino: str) -> str:
    """Lista los nombres de producto/variante que coincidan con un termino de
    busqueda (categoria o producto), sin el detalle de costeo. Usar cuando el
    usuario pide algo de forma generica por categoria (ej. 'una receta de masa
    quebrada') y hay que preguntarle cual variante especifica quiere."""
    return t.listar_variantes(termino)


@tool
def herramienta_buscar_receta(producto: str) -> str:
    """Busca el costeo y componentes de un producto por nombre (ej. 'Medialuna', 'Factura', 'Sandwich')."""
    return t.buscar_receta(producto)


@tool
def herramienta_escalar_ingredientes(producto: str, variante: str, cantidad: float) -> str:
    """Devuelve la lista de insumos y cantidades REALES (gramos/kg/L/unidades) para
    fabricar `cantidad` de un producto/variante -- para saber qué pesar/comprar.
    Usar esto (no herramienta_escalar_receta, que da el COSTO) cuando el usuario
    quiere hacer una receta a una cantidad específica."""
    return t.escalar_ingredientes(producto, variante, cantidad)


@tool
def herramienta_escalar_receta(
    producto: str, variante: str, cantidad: float, food_cost_objetivo: float | None = None
) -> str:
    """Calcula el costo de fabricar `cantidad` unidades de producto/variante.
    Si se da food_cost_objetivo (numero 0-100), calcula el precio de venta sugerido para ese food cost.
    Si no, usa el precio de venta actual del catalogo y muestra el food cost real."""
    return t.escalar_receta(producto, variante, cantidad, food_cost_objetivo)


@tool
def herramienta_registrar_produccion(fecha: str, producto: str, variante: str, cantidad: float) -> str:
    """Registra unidades producidas en un dia (formato fecha YYYY-MM-DD) y calcula su costo/ingreso."""
    return t.registrar_produccion(fecha, producto, variante, cantidad)


@tool
def herramienta_costo_diario(fecha: str) -> str:
    """Devuelve el costo, ingreso y ganancia total de produccion de un dia (formato YYYY-MM-DD)."""
    return t.costo_diario(fecha)


@tool
def herramienta_buscar_en_recetario(pregunta: str) -> str:
    """Busca en el recetario completo (ingredientes, procedimientos, notas) respuestas a preguntas abiertas."""
    vectorstore = load_index()
    docs = vectorstore.similarity_search(pregunta, k=3)
    return "\n---\n".join(d.page_content for d in docs)


TOOLS = [
    herramienta_estandarizar_receta_por_ingrediente,
    herramienta_agregar_ingrediente_receta,
    herramienta_eliminar_ingrediente_receta,
    herramienta_editar_ingrediente_receta,
    herramienta_reemplazar_ingrediente_receta,
    herramienta_escalar_ingredientes,
    herramienta_listar_variantes,
    herramienta_listar_precios_insumos,
    herramienta_actualizar_precio_insumo,
    herramienta_buscar_receta,
    herramienta_escalar_receta,
    herramienta_registrar_produccion,
    herramienta_costo_diario,
    herramienta_buscar_en_recetario,
]


def build_agent():
    llm = ChatCohere(
        model="command-a-03-2025",
        temperature=0,
        cohere_api_key=os.environ["COHERE_API_KEY"],
    )
    return create_agent(model=llm, tools=TOOLS, system_prompt=SYSTEM_PROMPT)


def ask(pregunta: str) -> str:
    graph = build_agent()
    resultado = graph.invoke({"messages": [("human", pregunta)]})
    return resultado["messages"][-1].content
