import logging
import sys

import structlog
from structlog.types import Processor

from fastapi_starter.core.logging.processors import (
    add_service_info,
    clean_event_dict,
    drop_color_message_key,
)


def get_processors(environment: str) -> list[Processor]:

    # Processors comuni a tutti gli ambienti
    # L'ordine è importante!
    shared_processors: list[Processor] = [
        # 1. Merge delle context variables (request_id, etc.)
        structlog.contextvars.merge_contextvars,
        # 2. Aggiunge il livello del log ("info", "error", etc.)
        structlog.processors.add_log_level,
        # 3. Aggiunge timestamp in formato ISO
        structlog.processors.TimeStamper(fmt="iso"),
        # 4. Aggiunge info sul servizio (nome, versione, ambiente)
        add_service_info,
        # 5. Rimuove chiavi interne
        clean_event_dict,
        # 6. Rimuove color_message di uvicorn
        drop_color_message_key,
    ]

    if environment == "development":
        # Sviluppo: output colorato e leggibile
        return shared_processors + [
            # Aggiunge info su file, linea, funzione (utile per debug)
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FILENAME,
                    structlog.processors.CallsiteParameter.LINENO,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                ]
            ),
            # Renderer colorato per console
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ]
    else:
        # Produzione/Staging: output JSON
        return shared_processors + [
            # Formatta le eccezioni come stringa
            structlog.processors.format_exc_info,
            # Output JSON
            structlog.processors.JSONRenderer(),
        ]


def configure_logging(
    environment: str = "development",
    log_level: str = "INFO",
) -> None:
    """
        Configura il sistema di logging per l'intera applicazione.

        Questa funzione deve essere chiamata UNA VOLTA all'avvio
        dell'applicazione, prima di qualsiasi log.

        Args:
            environment: "development", "staging", o "production"
            log_level: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"

        Example:
    ```python
            from fastapi_starter.core.logging import configure_logging

            configure_logging(
                environment="development",
                log_level="DEBUG",
            )
    ```
    """

    # Converti stringa a livello numerico
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Costruisci processors per l'ambiente
    processors = get_processors(environment)

    # Configura structlog
    structlog.configure(
        processors=processors,
        # Filtra log sotto il livello specificato
        wrapper_class=structlog.make_filtering_bound_logger(level),
        # Usa dict standard per il contesto
        context_class=dict,
        # Output su stdout
        logger_factory=structlog.PrintLoggerFactory(),
        # Cache del logger per performance
        cache_logger_on_first_use=True,
    )

    # Configura logging standard Python (per librerie esterne)
    # Questo fa sì che uvicorn, sqlalchemy, httpx, etc.
    # scrivano log nello stesso formato

    # Rimuovi handler esistenti
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Crea handler che scrive su stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    # Formato semplice — structlog gestisce il resto
    handler.setFormatter(logging.Formatter("%(message)s"))

    # Applica configurazione
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Silenzia log troppo verbosi di alcune librerie
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """
        Ottiene un logger configurato.

        Args:
            name: Nome opzionale del logger (es: nome del modulo).
                  Se non specificato, structlog lo determina automaticamente.

        Returns:
            Logger pronto all'uso

        Example:
    ```python
            from fastapi_starter.core.logging import get_logger

            logger = get_logger(__name__)
            logger.info("user_created", user_id=123)
    ```
    """
    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()
