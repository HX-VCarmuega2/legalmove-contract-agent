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

from src.retry import with_retries

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VISION_MODEL = "gpt-4o"

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
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return encoded, mime_type


@with_retries()
def parse_contract_image(image_path: str | Path, client: OpenAI | None = None) -> ParsedDocument:
    """Extrae el texto completo de un contrato escaneado usando GPT-4o Vision."""
    client = client or OpenAI()
    base64_image, mime_type = encode_image_to_base64(image_path)

    response = client.chat.completions.create(
        model=VISION_MODEL,
        temperature=0,
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

    text = response.choices[0].message.content or ""
    usage = response.usage.model_dump() if response.usage else {}

    return ParsedDocument(text=text, model=VISION_MODEL, usage=usage)
