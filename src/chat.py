"""CLI de prueba local del agente Malatesta."""
from .agent import build_agent


def main() -> None:
    graph = build_agent()
    messages = []
    print("Agente interno Malatesta. Escribe 'salir' para terminar.\n")
    while True:
        pregunta = input("Tú: ").strip()
        if pregunta.lower() in {"salir", "exit", "quit"}:
            break
        if not pregunta:
            continue
        messages.append(("human", pregunta))
        resultado = graph.invoke({"messages": messages})
        messages = resultado["messages"]
        respuesta = messages[-1].content
        print(f"Agente: {respuesta}\n")


if __name__ == "__main__":
    main()
