# Pipeline de Extracción de Entidades Técnicas

Pipeline LCEL que recibe un texto técnico sin procesar (descripción de arquitectura o log de error) y devuelve un objeto validado con Pydantic.

## Estructura

| Archivo | Contenido |
|---|---|
| `schemas.py` | Contrato Pydantic `ExtraccionTecnica` y enum `NivelCriticidad` |
| `chain.py` | `ChatPromptTemplate`, modelo `ChatOpenAI` / `ChatAnthropic`, cadena LCEL con `.with_structured_output()` y `.with_retry()`, función asíncrona `process_text()` |
| `main.py` | Script de prueba asíncrono con tres textos: arquitectura, log de error y texto ambiguo (prueba de estrés) |

## Esquema

| Campo | Tipo | Restricciones |
|---|---|---|
| `tecnologias` | `list[str]` | Al menos 1 elemento, sin vacíos ni duplicados |
| `nivel_de_criticidad` | `NivelCriticidad` | `baja`, `media` o `alta` |
| `resumen_tecnico` | `str` | Entre 20 y 400 caracteres |

El modelo usa `extra="forbid"`: cualquier campo adicional invalida la salida.

## Cadena LCEL

```python
modelo_estructurado = modelo.with_structured_output(ExtraccionTecnica, method="function_calling", include_raw=True)
extraccion_chain = prompt | modelo_estructurado
chain = RunnableLambda(registrar_intento) | extraccion_chain | RunnableLambda(validar_salida)
chain = chain.with_retry(retry_if_exception_type=ERRORES_REINTENTABLES, stop_after_attempt=3)
```

- `prompt` es un `ChatPromptTemplate` con dos variables: `texto` (entrada) e `instrucciones_formato` (inyectada con `.partial()`). No se usan f-strings para construir el prompt.
- `include_raw=True` conserva el mensaje original del modelo para revisar `finish_reason` y `parsing_error` antes de aceptar el objeto.
- `validar_salida` detecta respuestas cortadas por límite de tokens (`finish_reason` = `length` en OpenAI o `max_tokens` en Anthropic), JSON mal formado y salidas que no cumplen el esquema.

## Resiliencia

`.with_retry()` reintenta la cadena completa hasta 3 intentos, con espera exponencial, ante:

| Excepción | Causa |
|---|---|
| `OutputParserException` | JSON mal formado o salida vacía |
| `ValidationError` | El objeto no cumple el contrato Pydantic |
| `SalidaIncompletaError` | Respuesta cortada por límite de tokens |
| `LengthFinishReasonError` | Respuesta cortada por límite de tokens (OpenAI) |

Los errores de red y de límite de tasa los reintenta el cliente del proveedor (`max_retries=2`). Los errores de autenticación no se reintentan.

## Instalación

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

En Windows: `py -3.12 -m venv .venv`, `.venv\Scripts\activate` y `copy .env.example .env`.

## Variables de entorno

| Variable | Descripción |
|---|---|
| `LLM_PROVIDER` | `openai` o `anthropic` |
| `OPENAI_API_KEY` | API key de OpenAI |
| `ANTHROPIC_API_KEY` | API key de Anthropic |
| `LLM_MODEL` | Opcional. Por defecto `gpt-4.1-mini` o `claude-haiku-4-5` |
| `LLM_TEMPERATURE` | Opcional. Por defecto `0` |
| `LLM_MAX_TOKENS` | Opcional. Por defecto `1024` |

## Ejecución

```bash
python main.py
```

## Uso

```python
from chain import process_text

resultado = await process_text("Nuestra API en FastAPI usa Redis como caché y PostgreSQL...")
print(resultado.model_dump_json(indent=2))
```

## Ejemplo de salida

Entrada:

```
Nuestra API está construida con FastAPI y desplegada en Kubernetes. Usa Redis como caché y PostgreSQL como base de datos principal. Bajo carga alta las conexiones concurrentes a PostgreSQL se agotan y los tiempos de respuesta superan los 5 segundos en producción.
```

Salida:

```json
{
  "tecnologias": ["FastAPI", "Kubernetes", "Redis", "PostgreSQL"],
  "nivel_de_criticidad": "alta",
  "resumen_tecnico": "API en FastAPI sobre Kubernetes con caché en Redis y persistencia en PostgreSQL; las conexiones concurrentes se agotan bajo carga y degradan la respuesta en producción."
}
```

## Ejemplo de logs con reintento

```
INFO [pipeline] Procesando texto (225 caracteres)
INFO [pipeline] Intento de extracción: invocando LLM con salida estructurada
INFO [pipeline] Respuesta recibida (finish_reason=length)
WARNING [pipeline] Respuesta cortada por límite de tokens: objeto incompleto, se descarta
INFO [pipeline] Intento de extracción: invocando LLM con salida estructurada
INFO [pipeline] Respuesta recibida (finish_reason=tool_calls)
INFO [pipeline] Validación Pydantic OK: 4 tecnologías, criticidad=alta
INFO [pipeline] Texto procesado en 2.31s
```
