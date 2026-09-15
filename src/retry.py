"""Reintentos para llamadas a OpenAI que pueden fallar de forma transitoria."""
from __future__ import annotations

import time
from functools import wraps
from typing import Callable, TypeVar

import openai

T = TypeVar("T")

RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)


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
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except RETRYABLE_ERRORS as exc:
                    last_error = exc
                    if attempt == max_attempts:
                        break
                    time.sleep(backoff_seconds * attempt)
                except openai.AuthenticationError as exc:
                    raise RuntimeError(
                        "OPENAI_API_KEY inválida o ausente. Revisá tu archivo .env."
                    ) from exc
                except openai.BadRequestError as exc:
                    raise RuntimeError(f"Solicitud inválida a la API de OpenAI: {exc}") from exc
            raise RuntimeError(
                f"Falló la llamada a OpenAI tras {max_attempts} intentos: {last_error}"
            ) from last_error

        return wrapper

    return decorator
