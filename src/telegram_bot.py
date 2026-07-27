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

# Un AgentExecutor por chat, para que cada conversacion tenga su propio historial.
_executors: dict[int, object] = {}
_chat_histories: dict[int, list] = {}


def _get_executor(chat_id: int):
    if chat_id not in _executors:
        _executors[chat_id] = build_agent()
        _chat_histories[chat_id] = []
    return _executors[chat_id], _chat_histories[chat_id]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Agente interno Malatesta. Pregúntame por recetas, costos de "
        "fabricación para un pedido, o el costo de producción del día."
    )


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    pregunta = update.message.text
    executor, historial = _get_executor(chat_id)

    resultado = executor.invoke({"input": pregunta, "chat_history": historial})
    respuesta = resultado["output"]

    historial.append(("human", pregunta))
    historial.append(("ai", respuesta))

    await update.message.reply_text(respuesta)


def main() -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    app.run_polling()


if __name__ == "__main__":
    main()
