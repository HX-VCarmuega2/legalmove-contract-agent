"""Excepciones propias del pipeline.

Viven en su propio módulo para que `retry.py` (que define la política de
reintentos) y `image_parser.py` (que las lanza) puedan usarlas sin importarse
mutuamente.
"""
from __future__ import annotations


class TranscriptionRefusedError(RuntimeError):
    """El modelo no transcribió el documento y respondió otra cosa.

    Ocurre cuando GPT-4o contesta algo del tipo "Lo siento, no puedo ayudar
    con eso" en vez de la transcripción. Es un comportamiento intermitente:
    la misma imagen suele transcribirse bien en un reintento, así que se
    trata como un error transitorio.

    La excepción se lleva el `usage` de la llamada fallida, porque esos
    tokens se consumieron igual y de lo contrario no quedaría registro de
    ellos en ningún lado.
    """

    def __init__(self, message: str, usage: dict[str, int] | None = None) -> None:
        super().__init__(message)
        self.usage = usage or {}
