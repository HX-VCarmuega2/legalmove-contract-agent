"""Excepciones propias del pipeline.

Viven en su propio módulo para que `retry.py` (que define la política de
reintentos) y `image_parser.py` (que las lanza) puedan usarlas sin importarse
mutuamente.
"""
from __future__ import annotations


class ModelCallError(RuntimeError):
    """Fallo en una llamada que el modelo alcanzó a responder.

    Se lleva el `usage` de esa llamada, porque los tokens se consumieron
    igual: si no viajaran dentro de la excepción, la traza de Langfuse
    mostraría consumo cero en una etapa que en realidad se facturó.

    Hereda de RuntimeError para que `main.py` la siga atrapando junto con
    el resto de los errores de API, sin un except aparte.
    """

    def __init__(self, message: str, usage: dict[str, int] | None = None) -> None:
        super().__init__(message)
        self.usage = usage or {}


class TranscriptionRefusedError(ModelCallError):
    """El modelo no transcribió el documento y respondió otra cosa.

    Ocurre cuando GPT-4o contesta algo del tipo "Lo siento, no puedo ayudar
    con eso" en vez de la transcripción. Es un comportamiento intermitente:
    la misma imagen suele transcribirse bien en un reintento, así que se
    trata como un error transitorio y entra en la política de reintentos.
    """


class TranscriptionTruncatedError(ModelCallError):
    """La transcripción se cortó por el límite de tokens de salida.

    A diferencia de la negativa, no es transitorio: con el mismo límite el
    resultado se va a cortar siempre en el mismo lugar. Por eso queda fuera
    de RETRYABLE_ERRORS — reintentarlo solo gastaría tokens de nuevo.
    """
