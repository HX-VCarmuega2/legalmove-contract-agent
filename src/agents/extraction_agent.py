"""Agente 2: usa el mapa de contexto del Agente 1 para aislar y describir cambios.

Este es el "handoff": recibe el mapa de correspondencia que produjo el
ContextualizationAgent junto con ambos textos completos, y su única
responsabilidad es identificar cada cambio real y devolverlo en el formato
que exige ContractChangeOutput (validado por Pydantic vía structured output).
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.agents.results import ExtractionResult, normalize_usage
from src.models import ContractChangeOutput
from src.retry import with_retries

AGENT_MODEL = "gpt-4o"

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
- MODIFICACIÓN: una cláusula que existe en ambos documentos pero cuyo título o \
cuyo contenido (montos, plazos, alcance, partes, condiciones) cambió.

Método de trabajo, antes de redactar la respuesta:
Recorré el mapa de contexto par por par. Para cada par de cláusulas \
correspondientes, compará por separado:
a) el TÍTULO, y
b) el TEXTO, palabra por palabra: identificá qué palabras están en uno de los \
dos textos y no en el otro. Prestá especial atención a los calificativos que \
acotan o amplían una obligación (del tipo "irrevocable", "no reembolsable", \
"solidariamente", "indefinida"): si un calificativo así desapareció o \
apareció, es un cambio que debés reportar, aunque el resto de la oración sea \
casi igual.
Anotá todos los cambios encontrados y recién entonces redactá el resumen.

Cómo redactar el resumen:
Escribí una oración por cada cláusula que cambió, en el orden en que aparecen \
en el contrato. En cada oración citá textualmente la parte que cambió en los \
dos documentos, con el formato: de "<texto exacto del original>" a "<texto \
exacto de la enmienda>". Citá solo el fragmento relevante, no la cláusula \
entera. Si una cláusula tiene más de un cambio (por ejemplo, cambió el título \
y además el contenido, o se reescribió una frase y además se quitó una \
palabra), citá cada uno de esos cambios por separado dentro de la misma \
oración. Si la cláusula es nueva o fue eliminada, no hace falta citar: \
describí qué obligación se agrega o desaparece.

Reglas:
- Basate únicamente en lo que dicen los textos, nunca inventes cambios que no \
estén respaldados por el contenido.
- Si dos redacciones dicen literalmente lo mismo con otras palabras, NO es un \
cambio real. Quitar o agregar una palabra que cambia el alcance de una \
obligación SÍ es un cambio real.
- Sé específico en el resumen: mencioná montos, plazos o condiciones \
concretas, no generalidades como "se actualizaron algunos términos".
- En sections_changed, identificá cada sección por su número y título. Si el \
título cambió, usá el formato "N. Título original → Título nuevo". Si la \
sección es nueva, agregá "(nueva)"; si fue eliminada, agregá "(eliminada)".
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
        base_llm = llm or ChatOpenAI(model=AGENT_MODEL, temperature=0)
        # include_raw=True devuelve también el mensaje original del modelo, que
        # es de donde salen los tokens consumidos. Sin esto, LangChain entrega
        # solo el objeto parseado y esa métrica se pierde.
        self.structured_llm = base_llm.with_structured_output(
            ContractChangeOutput, include_raw=True
        )

    @with_retries()
    def run(self, context_map: str, original_text: str, amendment_text: str) -> ExtractionResult:
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
        response = self.structured_llm.invoke(messages)

        raw = response.get("raw")
        if raw is not None and raw.response_metadata.get("finish_reason") == "length":
            raise RuntimeError(
                "El Agente de Extracción se quedó sin tokens y su respuesta quedó "
                "truncada. Es probable que el contrato sea demasiado largo para una "
                "sola llamada."
            )

        # Con include_raw=True, un error de parseo no lanza excepción: queda
        # en parsing_error y "parsed" viene vacío. Lo convertimos en un error
        # explícito para que no siga viajando un None por el pipeline.
        if response.get("parsing_error") or response.get("parsed") is None:
            raise RuntimeError(
                "El Agente de Extracción no devolvió una respuesta que cumpla el schema: "
                f"{response.get('parsing_error')}"
            )

        return ExtractionResult(
            output=response["parsed"],
            usage=normalize_usage(response["raw"].usage_metadata),
        )
