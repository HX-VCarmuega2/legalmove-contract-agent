"""Entry point del pipeline de comparación de contratos.

Uso:
    python -m src.main <contrato_original.jpg> <enmienda.jpg>
"""
from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAIError
from pydantic import ValidationError

load_dotenv()

from langfuse import get_client

from src.agents.contextualization_agent import ContextualizationAgent
from src.agents.extraction_agent import ExtractionAgent
from src.image_parser import ParsedDocument, parse_contract_image, validate_image_path
from src.models import ContractChangeOutput

REQUIRED_ENV_VARS = ("OPENAI_API_KEY",)


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
            raw_result = extraction_agent.run(context_map, original_doc.text, amendment_doc.text)
            try:
                # Segunda validación explícita: aunque with_structured_output
                # ya fuerza el schema del lado del modelo, tratamos el output
                # del agente como un límite de confianza y lo re-validamos
                # antes de dejarlo salir del pipeline.
                result = ContractChangeOutput.model_validate(raw_result.model_dump())
            except ValidationError as exc:
                span.update(level="ERROR", status_message=str(exc))
                raise
            span.update(output=result.model_dump())

        root_span.update(output=result.model_dump())

    langfuse.flush()
    return result


def main() -> None:
    args = parse_args()
    try:
        # Fail fast: validamos credenciales y archivos ANTES de instanciar
        # agentes o llamar a cualquier API, para dar un error claro e
        # inmediato en vez de un traceback confuso a mitad de pipeline.
        missing_env = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
        if missing_env:
            raise RuntimeError(
                f"Faltan variables de entorno: {', '.join(missing_env)}. "
                "Copiá .env.example a .env y completá tus keys."
            )
        validate_image_path(args.original_path)
        validate_image_path(args.amendment_path)

        result = run_pipeline(args.original_path, args.amendment_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error de entrada: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValidationError as exc:
        print(
            f"El resultado del Agente de Extracción no cumple el schema esperado:\n{exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except (RuntimeError, OpenAIError) as exc:
        print(f"Error llamando a la API: {exc}", file=sys.stderr)
        sys.exit(1)

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
