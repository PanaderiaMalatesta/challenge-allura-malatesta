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
- NUNCA inventes ni calcules cifras de memoria. Todo número de costo, precio o
  food cost debe salir de las herramientas (escalar_receta, buscar_receta,
  registrar_produccion, costo_diario). Si una herramienta no tiene el dato,
  dilo claramente en vez de estimar.
- Si el usuario no especifica la variante de un producto (ej. solo dice
  "medialunas" sin decir cuál sabor), pregunta o usa buscar_receta para
  mostrar las variantes disponibles.
- Responde siempre en español, de forma directa y con las cifras en pesos
  chilenos (CLP).
"""


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
def herramienta_buscar_receta(producto: str) -> str:
    """Busca el costeo y componentes de un producto por nombre (ej. 'Medialuna', 'Factura', 'Sandwich')."""
    return t.buscar_receta(producto)


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
