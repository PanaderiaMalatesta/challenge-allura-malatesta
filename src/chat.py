"""CLI de prueba local del agente Malatesta."""
from .agent import build_agent


def main() -> None:
    executor = build_agent()
    chat_history = []
    print("Agente interno Malatesta. Escribe 'salir' para terminar.\n")
    while True:
        pregunta = input("Tú: ").strip()
        if pregunta.lower() in {"salir", "exit", "quit"}:
            break
        if not pregunta:
            continue
        resultado = executor.invoke({"input": pregunta, "chat_history": chat_history})
        respuesta = resultado["output"]
        print(f"Agente: {respuesta}\n")
        chat_history.append(("human", pregunta))
        chat_history.append(("ai", respuesta))


if __name__ == "__main__":
    main()
