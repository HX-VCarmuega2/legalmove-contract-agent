"""Agente 1: construye un mapa de correspondencia entre original y enmienda.

Este agente NO detecta cambios. Su única responsabilidad es entender cómo se
corresponden las secciones de ambos documentos entre sí, para que el segundo
agente (ExtractionAgent) no tenga que resolver esa alineación por su cuenta.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.retry import with_retries

_SYSTEM_PROMPT = """\
Sos un Analista Legal Senior especializado en derecho contractual, con años de \
experiencia comparando versiones de contratos comerciales.

Tu única responsabilidad es CONTEXTUALIZAR, no detectar cambios todavía. Dado \
el texto de un contrato original y el texto de su enmienda, producí un mapa \
de correspondencia de estructura:

1. Listá las secciones/cláusulas que existen en el documento original.
2. Listá las secciones/cláusulas que existen en la enmienda.
3. Indicá qué sección de la enmienda corresponde a qué sección del original \
(por número, título o contenido — los títulos pueden variar levemente entre \
versiones).
4. Señalá las secciones que aparecen SOLO en la enmienda (posibles adiciones) \
o SOLO en el original (posibles eliminaciones).
5. Para cada bloque, describí en una frase cuál es su propósito general \
(por ejemplo: "regula el plazo de vigencia del contrato").

No opines todavía sobre qué cambió en el contenido de cada cláusula ni \
redactes un resumen de cambios: eso lo hace otro analista a partir de tu mapa. \
Tu output es un insumo de trabajo interno, no un reporte final — usá texto \
estructurado (listas, encabezados), no hace falta que sea JSON.

Listá únicamente secciones que existan literalmente en el texto que te \
pasaron. No agregues secciones "típicas" de este tipo de contrato que no \
estén escritas en los documentos, aunque sean habituales en la práctica.
"""


class ContextualizationAgent:
    """Primer agente del pipeline: entiende la estructura, no el contenido cambiado."""

    def __init__(self, llm: ChatOpenAI | None = None) -> None:
        self.llm = llm or ChatOpenAI(model="gpt-4o", temperature=0)

    @with_retries()
    def run(self, original_text: str, amendment_text: str) -> str:
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "### CONTRATO ORIGINAL\n\n"
                    f"{original_text}\n\n"
                    "### ENMIENDA\n\n"
                    f"{amendment_text}\n\n"
                    "Generá el mapa de correspondencia de estructura entre ambos documentos."
                )
            ),
        ]
        response = self.llm.invoke(messages)
        return response.content
