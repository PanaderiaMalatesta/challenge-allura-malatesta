"""Agente interno de administracion Malatesta.

Combina:
- Herramientas deterministicas de costeo/inventario (tools.py) -- toda la
  matematica pasa por Python, nunca por el LLM.
- Un retriever sobre el recetario (ingest.py) para preguntas abiertas sobre
  ingredientes/procedimientos.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

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
def herramienta_buscar_receta(producto: str) -> str:
    """Busca el costeo y componentes de un producto por nombre (ej. 'Medialuna', 'Factura', 'Sandwich')."""
    return t.buscar_receta(producto)


@tool
def herramienta_escalar_receta(producto: str, variante: str, cantidad: float, food_cost_objetivo: float = None) -> str:
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


def build_agent() -> AgentExecutor:
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0,
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )

    tools = [
        herramienta_buscar_receta,
        herramienta_escalar_receta,
        herramienta_registrar_produccion,
        herramienta_costo_diario,
        herramienta_buscar_en_recetario,
    ]

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder("chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    agent = create_tool_calling_agent(llm, tools, prompt)
    return AgentExecutor(agent=agent, tools=tools, verbose=False)


def ask(pregunta: str) -> str:
    executor = build_agent()
    resultado = executor.invoke({"input": pregunta})
    return resultado["output"]
