"""Utilidades para leer contratos escaneados con el modelo de visión de OpenAI.

Paso 1 del pipeline: convierte una imagen (JPEG/PNG) en texto plano fiel al
documento original. Este módulo no interpreta el contenido legal ni compara
nada — esa responsabilidad es de los agentes (ver src/agents/).
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from src.config import VISION_MODEL
from src.errors import TranscriptionRefusedError, TranscriptionTruncatedError
from src.retry import with_retries

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# Primeros bytes que identifican a cada formato ("magic bytes"). Sirven para
# detectar un archivo corrupto o renombrado (un .txt con extensión .jpg) sin
# depender de una librería de imágenes.
MAGIC_BYTES = {
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".png": b"\x89PNG\r\n\x1a\n",
}

# Mínimo de caracteres que esperamos de la transcripción de un contrato.
# Por debajo de eso, asumimos que el modelo no transcribió sino que respondió
# otra cosa (una negativa, un mensaje de error).
MIN_TRANSCRIPTION_CHARS = 80

_SYSTEM_PROMPT = (
    "Sos un sistema OCR legal de alta precisión. Tu única tarea es transcribir "
    "el texto completo de la imagen de un contrato, de la forma más fiel posible "
    "al documento original.\n\n"
    "Reglas estrictas:\n"
    "- Conservá la estructura del documento: título y numeración de "
    "cláusulas/secciones, usando Markdown simple (## para encabezados de sección).\n"
    "- No resumas, no interpretes ni completes información faltante, y no "
    "corrijas errores del documento original.\n"
    "- Si una palabra es ilegible, marcala como [ilegible] en vez de inventarla.\n"
    "- No agregues comentarios ni texto que no esté en la imagen."
)


@dataclass
class ParsedDocument:
    """Resultado de parsear una imagen de contrato."""

    text: str
    model: str
    usage: dict[str, int]


def validate_image_path(image_path: str | Path) -> Path:
    """Valida que el archivo exista y sea un formato de imagen soportado."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró la imagen: {path}")
    if path.suffix.lower() not in VALID_EXTENSIONS:
        raise ValueError(
            f"Formato no soportado '{path.suffix}'. Usá uno de: {sorted(VALID_EXTENSIONS)}"
        )
    return path


def encode_image_to_base64(image_path: str | Path) -> tuple[str, str]:
    """Codifica una imagen en base64 y devuelve (base64_str, mime_type)."""
    path = validate_image_path(image_path)
    mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"

    try:
        with open(path, "rb") as f:
            content = f.read()
    except OSError as exc:
        raise ValueError(f"No se pudo leer la imagen {path}: {exc}") from exc

    if not content:
        raise ValueError(f"La imagen {path} está vacía (0 bytes).")

    expected_magic = MAGIC_BYTES[path.suffix.lower()]
    if not content.startswith(expected_magic):
        raise ValueError(
            f"El archivo {path} tiene extensión '{path.suffix}' pero su contenido no "
            "corresponde a ese formato: puede estar corrupto o mal renombrado."
        )

    return base64.b64encode(content).decode("utf-8"), mime_type


@with_retries()
def parse_contract_image(
    image_path: str | Path,
    client: OpenAI | None = None,
    max_tokens: int | None = None,
) -> ParsedDocument:
    """Extrae el texto completo de un contrato escaneado usando GPT-4o Vision.

    `max_tokens` limita la respuesta del modelo. En producción se deja en None;
    sirve para probar a propósito el caso de una transcripción truncada.
    """
    client = client or OpenAI()
    base64_image, mime_type = encode_image_to_base64(image_path)

    optional_params = {"max_completion_tokens": max_tokens} if max_tokens else {}

    response = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0,
        **optional_params,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Transcribí el texto completo de este contrato."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
    )

    choice = response.choices[0]
    usage = response.usage.model_dump() if response.usage else {}

    # finish_reason == "length" significa que el modelo se quedó sin tokens y
    # la transcripción quedó cortada. Devolverla sería peor que fallar: los
    # agentes compararían contra un contrato incompleto y reportarían como
    # eliminadas cláusulas que en realidad no se alcanzaron a transcribir.
    if choice.finish_reason == "length":
        raise TranscriptionTruncatedError(
            f"La transcripción de {image_path} quedó truncada por el límite de tokens. "
            "Probá con una imagen de menor resolución o subí el límite de salida.",
            usage=usage,
        )

    text = choice.message.content or ""

    # El modelo puede responder algo tipo "Lo siento, no puedo ayudar con eso"
    # en vez de transcribir (por ejemplo, si la imagen es ilegible o si se
    # niega). Eso termina "normalmente", así que finish_reason no lo detecta.
    # Un contrato transcripto nunca es tan corto: si lo es, algo salió mal y
    # es preferible cortar acá que pasarle un texto basura a los agentes.
    if len(text.strip()) < MIN_TRANSCRIPTION_CHARS:
        raise TranscriptionRefusedError(
            f"La transcripción de {image_path} es sospechosamente corta "
            f"({len(text.strip())} caracteres). El modelo puede no haber podido leer "
            f"la imagen. Respuesta recibida: {text.strip()!r}",
            usage=usage,
        )

    return ParsedDocument(text=text, model=VISION_MODEL, usage=usage)
