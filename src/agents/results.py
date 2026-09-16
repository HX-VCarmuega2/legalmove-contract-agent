"""Tipos de retorno de los agentes: resultado más consumo de tokens.

Los agentes devuelven también el `usage` para que main.py pueda registrar en
Langfuse los tokens reales informados por la API, en vez de dejar que Langfuse
los estime a partir del texto del span.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.models import ContractChangeOutput


def normalize_usage(usage_metadata: dict[str, Any] | None) -> dict[str, int]:
    """Convierte el usage_metadata de LangChain al formato que espera Langfuse.

    LangChain devuelve input_tokens/output_tokens/total_tokens y, además,
    diccionarios anidados con el detalle. Langfuse espera un diccionario plano
    de enteros, así que nos quedamos solo con los tres totales.
    """
    usage = usage_metadata or {}
    return {
        "input": int(usage.get("input_tokens", 0)),
        "output": int(usage.get("output_tokens", 0)),
        "total": int(usage.get("total_tokens", 0)),
    }


@dataclass
class ContextResult:
    """Salida del ContextualizationAgent."""

    context_map: str
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Salida del ExtractionAgent."""

    output: ContractChangeOutput
    usage: dict[str, int] = field(default_factory=dict)
