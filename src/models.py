"""Modelos Pydantic para la salida validada del pipeline."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ContractChangeOutput(BaseModel):
    """Resultado estructurado y validado que produce el ExtractionAgent.

    Este modelo es el contrato de datos entre el sistema de IA y los sistemas
    downstream de LegalMove (por ejemplo, el sistema que deriva el caso a un
    abogado de Compliance). Por eso los tres campos son obligatorios: si el
    modelo de lenguaje no los completa, Pydantic debe rechazar la respuesta
    antes de que llegue a producción, en vez de dejar pasar un JSON incompleto.
    """

    sections_changed: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Identificadores o títulos de las secciones/cláusulas del contrato "
            "que fueron modificadas, agregadas o eliminadas por la enmienda. "
            "Ejemplo: ['2. Plazo', '3. Pago', '7. Protección de Datos (nueva)']."
        ),
    )
    topics_touched: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Categorías legales o comerciales afectadas por los cambios. "
            "Ejemplo: ['plazo contractual', 'condiciones de pago', 'protección de datos']."
        ),
    )
    summary_of_the_change: str = Field(
        ...,
        min_length=1,
        description=(
            "Resumen preciso y en lenguaje natural de qué cambió entre el "
            "contrato original y la enmienda, y por qué es relevante para "
            "el equipo de Compliance."
        ),
    )
