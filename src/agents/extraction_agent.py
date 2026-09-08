"""Agente 2: usa el mapa de contexto del Agente 1 para aislar y describir cambios.

Este es el "handoff": recibe el mapa de correspondencia que produjo el
ContextualizationAgent junto con ambos textos completos, y su única
responsabilidad es identificar cada cambio real y devolverlo en el formato
que exige ContractChangeOutput (validado por Pydantic vía structured output).
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.models import ContractChangeOutput

_SYSTEM_PROMPT = """\
Sos un Auditor Legal especializado en control de cambios (redlining) de \
contratos comerciales. Trabajás en equipo con un Analista de \
Contextualización: él ya te entregó un mapa de correspondencia entre el \
contrato original y la enmienda, indicando qué sección de uno corresponde a \
cuál del otro.

Tu única responsabilidad es, usando ese mapa como guía, identificar cada \
cambio real introducido por la enmienda y clasificarlo en:
- ADICIÓN: una cláusula, obligación o condición que no existía en el original.
- ELIMINACIÓN: una cláusula, obligación o condición del original que \
desapareció en la enmienda.
- MODIFICACIÓN: una cláusula que existe en ambos documentos pero cuyo \
contenido (montos, plazos, alcance, partes, condiciones) cambió.

Reglas:
- Basate únicamente en lo que dicen los textos, nunca inventes cambios que no \
estén respaldados por el contenido.
- Si dos redacciones dicen literalmente lo mismo con otras palabras, NO es un \
cambio real.
- Sé específico en el resumen: mencioná montos, plazos o condiciones \
concretas, no generalidades como "se actualizaron algunos términos".
- Tu respuesta debe cumplir exactamente el schema indicado (sections_changed, \
topics_touched, summary_of_the_change).

Verificación obligatoria antes de responder: por cada cambio que vayas a \
reportar, releé el CONTRATO ORIGINAL y la ENMIENDA y confirmá que podés citar \
la frase o cifra exacta que lo respalda en al menos uno de los dos textos (o \
su ausencia, si es una adición o eliminación). Si no podés señalar esa \
evidencia textual concreta, NO incluyas ese cambio, aunque te parezca \
plausible o típico de este tipo de contrato. Nunca completes con contenido \
"esperable" que no esté escrito literalmente en los documentos.
"""


class ExtractionAgent:
    """Segundo agente del pipeline: hace el handoff desde el mapa de contexto al JSON final."""

    def __init__(self, llm: ChatOpenAI | None = None) -> None:
        base_llm = llm or ChatOpenAI(model="gpt-4o", temperature=0)
        self.structured_llm = base_llm.with_structured_output(ContractChangeOutput)

    def run(self, context_map: str, original_text: str, amendment_text: str) -> ContractChangeOutput:
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "### MAPA DE CONTEXTO (del Analista de Contextualización)\n\n"
                    f"{context_map}\n\n"
                    "### CONTRATO ORIGINAL\n\n"
                    f"{original_text}\n\n"
                    "### ENMIENDA\n\n"
                    f"{amendment_text}\n\n"
                    "Identificá los cambios y devolvé el resultado estructurado."
                )
            ),
        ]
        return self.structured_llm.invoke(messages)
