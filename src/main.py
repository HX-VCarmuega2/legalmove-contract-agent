"""Entry point del pipeline de comparación de contratos.

Uso:
    python -m src.main <contrato_original.jpg> <enmienda.jpg>
"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv

load_dotenv()

from langfuse import get_client

from src.agents.contextualization_agent import ContextualizationAgent
from src.agents.extraction_agent import ExtractionAgent
from src.image_parser import ParsedDocument, parse_contract_image
from src.models import ContractChangeOutput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara un contrato original y su enmienda, y devuelve un JSON con los cambios."
    )
    parser.add_argument("original_path", help="Path a la imagen del contrato original (JPEG/PNG)")
    parser.add_argument("amendment_path", help="Path a la imagen de la enmienda (JPEG/PNG)")
    return parser.parse_args()


def _traced_parse(langfuse, span_name: str, image_path: str) -> ParsedDocument:
    """Corre parse_contract_image() dentro de un span hijo de Langfuse."""
    with langfuse.start_as_current_observation(
        name=span_name,
        as_type="generation",
        model="gpt-4o",
        input={"image_path": image_path},
    ) as span:
        doc = parse_contract_image(image_path)
        span.update(output=doc.text, usage_details=doc.usage)
        return doc


def run_pipeline(original_path: str, amendment_path: str) -> ContractChangeOutput:
    """Ejecuta el pipeline completo: parsing -> Agente 1 -> Agente 2."""
    langfuse = get_client()

    with langfuse.start_as_current_observation(
        name="contract-analysis",
        as_type="span",
        input={"original_path": original_path, "amendment_path": amendment_path},
    ) as root_span:

        original_doc = _traced_parse(langfuse, "parse_original_contract", original_path)
        amendment_doc = _traced_parse(langfuse, "parse_amendment_contract", amendment_path)

        with langfuse.start_as_current_observation(
            name="contextualization_agent",
            as_type="generation",
            model="gpt-4o",
            input={"original_text": original_doc.text, "amendment_text": amendment_doc.text},
        ) as span:
            context_agent = ContextualizationAgent()
            context_map = context_agent.run(original_doc.text, amendment_doc.text)
            span.update(output=context_map)

        with langfuse.start_as_current_observation(
            name="extraction_agent",
            as_type="generation",
            model="gpt-4o",
            input={"context_map": context_map},
        ) as span:
            extraction_agent = ExtractionAgent()
            result = extraction_agent.run(context_map, original_doc.text, amendment_doc.text)
            span.update(output=result.model_dump())

        root_span.update(output=result.model_dump())

    langfuse.flush()
    return result


def main() -> None:
    args = parse_args()
    result = run_pipeline(args.original_path, args.amendment_path)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
