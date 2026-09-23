"""Reintentos para llamadas a OpenAI que pueden fallar de forma transitoria."""
from __future__ import annotations

import sys
import time
from functools import wraps
from typing import Callable, TypeVar

import openai

from src.errors import TranscriptionRefusedError

T = TypeVar("T")

# Cuánto del mensaje de error guardamos como motivo del reintento. El mensaje
# de TranscriptionRefusedError termina con la respuesta textual del modelo
# ("Respuesta recibida: ..."), que es lo primero que uno quiere ver en la
# traza: con menos de esto, el corte cae justo antes de esa parte.
MAX_REASON_CHARS = 300

RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
    # La negativa del modelo a transcribir es intermitente: con la misma
    # imagen, un reintento suele funcionar.
    TranscriptionRefusedError,
)


def _sum_wasted_tokens(errors: list[Exception]) -> dict[str, int]:
    """Suma los tokens consumidos por los intentos que fallaron.

    Solo algunos errores traen consumo: si la llamada falló por rate limit o
    timeout, no se gastaron tokens. En cambio, si el modelo respondió pero se
    negó a transcribir, esos tokens se pagaron igual.
    """
    wasted = {"input": 0, "output": 0, "total": 0}
    for error in errors:
        usage = getattr(error, "usage", None) or {}
        wasted["input"] += usage.get("prompt_tokens", 0)
        wasted["output"] += usage.get("completion_tokens", 0)
        wasted["total"] += usage.get("total_tokens", 0)
    return wasted


def _record_retries(reasons: list[str], errors: list[Exception]) -> None:
    """Deja constancia de los reintentos en el span de Langfuse en curso.

    Sin esto, un reintento solo se nota como "esta etapa tardó más": la traza
    no muestra que hubo un fallo intermedio ni por qué. Se marca el span como
    WARNING para poder filtrarlos en el dashboard.

    Se importa Langfuse acá adentro y no arriba para que este módulo siga
    sirviendo aunque no haya trazabilidad configurada.
    """
    try:
        from langfuse import get_client

        get_client().update_current_span(
            level="WARNING",
            metadata={
                "retry_count": len(reasons),
                "retry_reasons": reasons,
                "wasted_tokens": _sum_wasted_tokens(errors),
            },
        )
    except Exception:  # noqa: BLE001 - registrar nunca debe romper el pipeline
        pass


def with_retries(max_attempts: int = 3, backoff_seconds: float = 2.0) -> Callable:
    """Reintenta una llamada ante errores transitorios (rate limit, timeout, 5xx).

    No reintenta errores no recuperables (API key inválida, request mal
    formado): esos fallan inmediatamente y con un mensaje claro, en vez de
    esconderse detrás de reintentos que de todas formas van a fallar.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error: Exception | None = None
            reasons: list[str] = []
            errors: list[Exception] = []
            for attempt in range(1, max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                except RETRYABLE_ERRORS as exc:
                    last_error = exc
                    errors.append(exc)
                    reason = f"{type(exc).__name__}: {str(exc)[:MAX_REASON_CHARS]}"
                    reasons.append(reason)
                    if attempt == max_attempts:
                        break
                    print(
                        f"\n  reintento {attempt}/{max_attempts - 1} por {reason}",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(backoff_seconds * attempt)
                except openai.AuthenticationError as exc:
                    raise RuntimeError(
                        "OPENAI_API_KEY inválida o ausente. Revisá tu archivo .env."
                    ) from exc
                except openai.BadRequestError as exc:
                    raise RuntimeError(f"Solicitud inválida a la API de OpenAI: {exc}") from exc
                else:
                    # El else de un try corre solo si no hubo excepción, y va
                    # después de todos los except.
                    if reasons:
                        _record_retries(reasons, errors)
                    return result
            # También registramos cuando se agotaron los intentos: es el
            # momento en que más importa saber qué pasó en cada uno.
            _record_retries(reasons, errors)
            raise RuntimeError(
                f"Falló la llamada a OpenAI tras {max_attempts} intentos: {last_error}"
            ) from last_error

        return wrapper

    return decorator
