"""Entry point del pipeline de comparación de contratos.

Uso:
    python -m src.main <contrato_original.jpg> <enmienda.jpg>
"""
from __future__ import annotations

import argparse

from dotenv import load_dotenv

load_dotenv()

from src.agents.contextualization_agent import ContextualizationAgent
from src.agents.extraction_agent import ExtractionAgent
from src.image_parser import parse_contract_image
from src.models import ContractChangeOutput


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara un contrato original y su enmienda, y devuelve un JSON con los cambios."
    )
    parser.add_argument("original_path", help="Path a la imagen del contrato original (JPEG/PNG)")
    parser.add_argument("amendment_path", help="Path a la imagen de la enmienda (JPEG/PNG)")
    return parser.parse_args()


def run_pipeline(original_path: str, amendment_path: str) -> ContractChangeOutput:
    """Ejecuta el pipeline completo: parsing -> Agente 1 -> Agente 2."""
    original_doc = parse_contract_image(original_path)
    amendment_doc = parse_contract_image(amendment_path)

    context_agent = ContextualizationAgent()
    context_map = context_agent.run(original_doc.text, amendment_doc.text)

    extraction_agent = ExtractionAgent()
    result = extraction_agent.run(context_map, original_doc.text, amendment_doc.text)

    return result


def main() -> None:
    args = parse_args()
    result = run_pipeline(args.original_path, args.amendment_path)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
