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

    # Los ejemplos de las descripciones usan secciones y temas que no aparecen
    # en ningún contrato de prueba ni en las evals: las descripciones viajan al
    # modelo como parte del schema, y un ejemplo tomado de un caso de prueba
    # le daría parte de la respuesta correcta.
    # Las listas pueden venir vacías a propósito: es la única forma de que el
    # sistema pueda responder "no hay cambios" sin inventar uno para cumplir el
    # schema. Con min_length=1, al comparar un contrato contra sí mismo el
    # modelo llenaba las listas con todas las secciones.
    sections_changed: list[str] = Field(
        ...,
        description=(
            "Secciones/cláusulas del contrato que fueron modificadas, agregadas o "
            "eliminadas por la enmienda, identificadas por número y título. Si la "
            "sección cambió de título, usar 'N. Título original → Título nuevo'; si "
            "es nueva, agregar '(nueva)'; si fue eliminada, agregar '(eliminada)'. "
            "Ejemplo: ['4. Garantías', '8. Penalidades → Multas por Incumplimiento', "
            "'10. Seguros (nueva)', '6. Cesión de Derechos (eliminada)']. "
            "Lista vacía si la enmienda no introduce ningún cambio."
        ),
    )
    topics_touched: list[str] = Field(
        ...,
        description=(
            "Categorías legales o comerciales afectadas por los cambios. "
            "Ejemplo: ['garantías', 'penalidades por incumplimiento', 'cobertura de seguros']."
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
