import asyncio
import logging

from dotenv import load_dotenv

from chain import process_text

TEXTOS = {
    "Descripción de arquitectura": (
        "Nuestra API está construida con FastAPI y desplegada en Kubernetes. "
        "Usa Redis como caché y PostgreSQL como base de datos principal. "
        "Bajo carga alta las conexiones concurrentes a PostgreSQL se agotan "
        "y los tiempos de respuesta superan los 5 segundos en producción."
    ),
    "Log de error": (
        "2026-10-05 14:32:11 ERROR [payment-service] "
        "kafka.errors.KafkaTimeoutError: Failed to update metadata after 60.0 secs. "
        "Spring Boot consumer stopped. 1.250 transacciones pendientes en la cola. "
        "Stripe webhook retries exhausted."
    ),
    "Prueba de estrés (texto ambiguo)": (
        "a veces anda lento, creo que es la base o el server, "
        "lo reiniciamos y se arregló, no sé si volverá a pasar"
    ),
}


async def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    for nombre in ("httpx", "httpx2"):
        logging.getLogger(nombre).setLevel(logging.WARNING)

    for titulo, texto in TEXTOS.items():
        print("\n" + "=" * 70)
        print(titulo)
        print("=" * 70)
        try:
            resultado = await process_text(texto)
            print(resultado.model_dump_json(indent=2))
        except Exception as exc:
            print("Error en el pipeline:", type(exc).__name__, exc)


if __name__ == "__main__":
    asyncio.run(main())
