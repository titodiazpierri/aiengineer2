import logging
import os
import time

from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from openai import LengthFinishReasonError
from pydantic import ValidationError

from schemas import ExtraccionTecnica

logger = logging.getLogger("pipeline")

MODELOS_POR_DEFECTO = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-4-5",
}

FINISH_REASONS_INCOMPLETOS = {"length", "max_tokens"}

INSTRUCCIONES_FORMATO = (
    "Devolvé únicamente el objeto estructurado con estos campos:\n"
    "- tecnologias: lista no vacía con cada tecnología mencionada, sin repetir.\n"
    "- nivel_de_criticidad: baja, media o alta.\n"
    "- resumen_tecnico: una o dos oraciones en español.\n"
    "Criterios de criticidad: alta si hay caída de servicio, pérdida de datos, "
    "riesgo de seguridad o impacto en producción; media si hay degradación de "
    "rendimiento o errores recuperables; baja si es informativo o sin impacto."
)

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Sos un ingeniero de software senior especializado en extraer "
            "entidades técnicas de textos sin procesar, como descripciones de "
            "arquitectura o logs de error.\n\n{instrucciones_formato}",
        ),
        ("human", "Texto a analizar:\n\n{texto}"),
    ]
).partial(instrucciones_formato=INSTRUCCIONES_FORMATO)


class SalidaIncompletaError(Exception):
    pass


ERRORES_REINTENTABLES = (
    OutputParserException,
    ValidationError,
    SalidaIncompletaError,
    LengthFinishReasonError,
)


def crear_modelo() -> BaseChatModel:
    proveedor = os.getenv("LLM_PROVIDER", "openai").lower()
    modelo = os.getenv("LLM_MODEL") or MODELOS_POR_DEFECTO.get(proveedor)
    parametros = {
        "model": modelo,
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "1024")),
        "timeout": 30,
        "max_retries": 2,
    }
    if proveedor == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(**parametros)
    if proveedor == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(**parametros)
    raise ValueError("LLM_PROVIDER inválido: " + proveedor + ". Usar openai o anthropic")


def obtener_finish_reason(raw) -> str | None:
    metadata = getattr(raw, "response_metadata", {}) or {}
    return metadata.get("finish_reason") or metadata.get("stop_reason")


def validar_salida(resultado: dict) -> ExtraccionTecnica:
    finish_reason = obtener_finish_reason(resultado.get("raw"))
    logger.info("Respuesta recibida (finish_reason=%s)", finish_reason)

    if finish_reason in FINISH_REASONS_INCOMPLETOS:
        logger.warning("Respuesta cortada por límite de tokens: objeto incompleto, se descarta")
        raise SalidaIncompletaError("Respuesta incompleta (finish_reason=" + str(finish_reason) + ")")

    error = resultado.get("parsing_error")
    if error:
        detalle = " | ".join(linea.strip() for linea in str(error).splitlines()[:3])
        logger.warning("JSON mal formado o que no cumple el esquema: %s", detalle)
        raise OutputParserException(str(error))

    parsed = resultado.get("parsed")
    if parsed is None:
        logger.warning("El modelo no devolvió un objeto estructurado")
        raise OutputParserException("Salida estructurada vacía")

    extraccion = ExtraccionTecnica.model_validate(parsed)
    logger.info("Validación Pydantic OK: %d tecnologías, criticidad=%s",
                len(extraccion.tecnologias), extraccion.nivel_de_criticidad)
    return extraccion


def registrar_intento(entrada: dict) -> dict:
    logger.info("Intento de extracción: invocando LLM con salida estructurada")
    return entrada


def construir_cadena(modelo: BaseChatModel | None = None) -> Runnable:
    modelo = modelo or crear_modelo()
    modelo_estructurado = modelo.with_structured_output(
        ExtraccionTecnica,
        method="function_calling",
        include_raw=True,
    )
    extraccion_chain = prompt | modelo_estructurado
    chain = RunnableLambda(registrar_intento) | extraccion_chain | RunnableLambda(validar_salida)
    return chain.with_retry(
        retry_if_exception_type=ERRORES_REINTENTABLES,
        stop_after_attempt=3,
        wait_exponential_jitter=True,
    )


_cadena: Runnable | None = None


async def process_text(text: str) -> ExtraccionTecnica:
    global _cadena
    if _cadena is None:
        _cadena = construir_cadena()

    logger.info("Procesando texto (%d caracteres)", len(text))
    inicio = time.perf_counter()
    try:
        resultado = await _cadena.ainvoke({"texto": text})
    except ERRORES_REINTENTABLES as exc:
        logger.error("Validación fallida tras agotar los reintentos: %s", type(exc).__name__)
        raise
    except Exception as exc:
        logger.error("Error del proveedor LLM (no reintentable por validación): %s", type(exc).__name__)
        raise
    logger.info("Texto procesado en %.2fs", time.perf_counter() - inicio)
    return resultado
