# Agente Interno Malatesta — Challenge Allura

Agente de IA para la administración interna de la Panadería Artesanal Malatesta
(Villarrica, Chile). No es un chatbot de atención al cliente: lo usan el dueño
o el panadero para consultar recetas, calcular el costo de fabricación al
escalar un pedido a una cantidad específica (ej. un evento con 50 medialunas),
y llevar el registro diario de producción/costo de insumos.

## Arquitectura

```
challenge Allura/
├── data/
│   ├── recetas.md              # recetario en texto (ingredientes, procedimiento)
│   ├── costeo_unitario.csv     # costo unitario por componente, por producto/variante
│   ├── precios_insumos.csv     # precio de cada materia prima
│   └── produccion_diaria.csv   # log de producción diaria (se alimenta solo)
├── src/
│   ├── tools.py     # cálculo determinístico: escalado, costeo, food cost, inventario
│   ├── ingest.py     # indexa recetas.md en un vector store (FAISS) para búsqueda semántica
│   ├── agent.py      # agente LangChain (Gemini) que combina el retriever + las tools
│   ├── chat.py       # CLI de prueba local
│   ├── server.py     # API FastAPI + página web mínima, para el deploy en OCI
│   └── static/index.html
├── deploy/            # instrucciones de despliegue en OCI Compute
└── requirements.txt
```

**Por qué este diseño:** el LLM (Gemini) nunca calcula números de memoria. Toda
la matemática de costeo, escalado y food cost vive en `tools.py`, que lee los
CSV de datos reales del negocio. El LLM solo decide qué herramienta llamar y
redacta la respuesta en español. Esto evita que el agente "invente" cifras de
costos, algo crítico cuando el resultado se usa para negociar precios con
clientes.

- **Documento (parte 1 del challenge):** `data/recetas.md`, con las recetas e
  ingredientes reales ya costeados en el plan de negocios de Malatesta
  (facturas, medialunas, sándwiches).
- **Agente (parte 2):** LangChain + Gemini (`gemini-2.0-flash`), con 5
  herramientas: búsqueda de receta, escalado/costeo, búsqueda semántica en el
  recetario, registro de producción diaria, y cálculo de costo diario.
- **Deploy (parte 3):** FastAPI + Uvicorn en una instancia OCI Compute (Always
  Free), con una página web mínima para consultar el agente desde el
  navegador. Ver `deploy/oci_setup.md`.

## Ejemplos de preguntas y respuestas

| Pregunta | Qué hace el agente |
|---|---|
| "¿Cuánto me cuesta hacer 50 medialunas de pistacho para un evento?" | Llama a `escalar_receta(Medialuna, Pistacho, 50)` → costo total real, precio actual e ingreso, food cost. |
| "Un cliente quiere 200 facturas surtidas, ¿a qué precio se las vendo para tener 25% de food cost?" | Llama a `escalar_receta` con `food_cost_objetivo=25` → precio de venta sugerido. |
| "¿De qué está hecha la medialuna de chocotorta?" | Busca en el recetario (`buscar_en_recetario`) y responde con los ingredientes reales. |
| "Hoy hicimos 40 facturas de manjar y 30 medialunas clásicas de dulce de leche" | Llama a `registrar_produccion` dos veces, guarda el consumo derivado en `produccion_diaria.csv`. |
| "¿Cuál fue el costo de producción de hoy?" | Llama a `costo_diario` y suma todo lo registrado ese día. |

## Cómo correrlo localmente

1. Crear entorno e instalar dependencias:
   ```powershell
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. Conseguir una API key gratuita de Gemini en [Google AI Studio](https://aistudio.google.com/apikey)
   y copiarla a un archivo `.env` (basado en `.env.example`):
   ```
   GOOGLE_API_KEY=tu_key_aqui
   ```
3. Construir el índice de búsqueda del recetario:
   ```powershell
   python -m src.ingest
   ```
4. Probar por consola:
   ```powershell
   python -m src.chat
   ```
5. O levantar el servidor local:
   ```powershell
   uvicorn src.server:app --reload
   ```
   y abrir `http://localhost:8000` en el navegador.

## Deploy en OCI

Ver [`deploy/oci_setup.md`](deploy/oci_setup.md) para el paso a paso de la
instancia Compute. Link/captura de la app corriendo en la nube:

> _Pendiente — se agrega una vez creada la instancia OCI._

## Próximos pasos (fuera del alcance de este challenge)

- Integración con WhatsApp Business para consultar el agente desde el celular.
- Cargar recetas de tortas y pan de masa madre (Club del Pan) cuando estén
  costeadas con cantidades reales.
