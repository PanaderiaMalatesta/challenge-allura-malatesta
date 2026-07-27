"""Bot de Telegram -- interfaz principal del agente interno Malatesta.

Usa long-polling (sin webhook), asi que en OCI no hace falta abrir ningun
puerto: el servidor solo hace conexiones salientes hacia la API de Telegram.
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .agent import build_agent

load_dotenv()
logging.basicConfig(level=logging.INFO)

# Un grafo de agente + historial de mensajes por chat, para que cada
# conversacion de Telegram tenga su propio contexto.
_graph = None
_chat_messages: dict[int, list] = {}


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_agent()
    return _graph


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Agente interno Malatesta. Pregúntame por recetas, costos de "
        "fabricación para un pedido, o el costo de producción del día."
    )


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    pregunta = update.message.text

    graph = _get_graph()
    messages = _chat_messages.setdefault(chat_id, [])
    messages.append(("human", pregunta))

    resultado = graph.invoke({"messages": messages})
    _chat_messages[chat_id] = resultado["messages"]
    respuesta = resultado["messages"][-1].content

    await update.message.reply_text(respuesta)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    app.run_polling()


if __name__ == "__main__":
    main()
