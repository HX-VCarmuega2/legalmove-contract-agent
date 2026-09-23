"""Entry point del pipeline de comparación de contratos.

Uso (las dos formas son equivalentes):
    python src/main.py <contrato_original.jpg> <enmienda.jpg>
    python -m src.main <contrato_original.jpg> <enmienda.jpg>
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# Si el archivo se ejecuta directamente (python src/main.py), Python agrega
# src/ al path de búsqueda en vez de la raíz del proyecto, y los imports
# "from src.xxx" no resuelven. Agregamos la raíz a mano para que las dos
# formas de ejecución funcionen igual.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from openai import OpenAIError
from pydantic import ValidationError

load_dotenv()

from langfuse import get_client

from src.agents.contextualization_agent import ContextualizationAgent
from src.agents.extraction_agent import ExtractionAgent
from src.config import AGENT_MODEL, VISION_MODEL
from src.image_parser import ParsedDocument, parse_contract_image, validate_image_path
from src.models import ContractChangeOutput

REQUIRED_ENV_VARS = ("OPENAI_API_KEY",)
PIPELINE_VERSION = "1.0"
TOTAL_STEPS = 4

# En Windows la consola suele usar cp1252, que no puede representar caracteres
# como "→" (lo usamos para las secciones renombradas) ni algunos acentos. Sin
# esto, el programa puede fallar con UnicodeEncodeError justo al imprimir el
# resultado, o al redirigir la salida a un archivo.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara un contrato original y su enmienda, y devuelve un JSON con los cambios."
    )
    parser.add_argument("original_path", help="Path a la imagen del contrato original (JPEG/PNG)")
    parser.add_argument("amendment_path", help="Path a la imagen de la enmienda (JPEG/PNG)")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="No muestra el progreso de cada etapa (stdout sigue siendo solo el JSON)",
    )
    return parser.parse_args()


@contextmanager
def step(number: int, description: str, *, quiet: bool):
    """Muestra el progreso de una etapa y cuánto tardó.

    El progreso va a stderr, nunca a stdout: así la salida estándar queda
    con el JSON puro y el comando se puede redirigir a un archivo o
    encadenar con otro proceso sin que el progreso lo ensucie.
    """
    if quiet:
        yield
        return

    print(f"[{number}/{TOTAL_STEPS}] {description}... ", end="", file=sys.stderr, flush=True)
    started = time.perf_counter()
    try:
        yield
    except Exception:
        print("ERROR", file=sys.stderr, flush=True)
        raise
    print(f"{time.perf_counter() - started:.1f}s", file=sys.stderr, flush=True)


def _traced_parse(langfuse, span_name: str, image_path: str) -> ParsedDocument:
    """Corre parse_contract_image() dentro de un span hijo de Langfuse."""
    path = Path(image_path)
    with langfuse.start_as_current_observation(
        name=span_name,
        as_type="generation",
        model=VISION_MODEL,
        input={"image_path": image_path},
        metadata={
            "file_name": path.name,
            "file_size_kb": round(path.stat().st_size / 1024, 1),
            "image_detail": "high",
        },
    ) as span:
        try:
            doc = parse_contract_image(image_path)
        except Exception as exc:
            # Si la etapa falla, informamos el consumo explícitamente. Sin
            # esto, Langfuse lo estima a partir del texto del span y muestra
            # un gasto que no corresponde. Hay dos casos distintos:
            #   - falló antes de llamar al modelo (archivo corrupto): cero;
            #   - el modelo respondió (se negó a transcribir, o la respuesta
            #     quedó truncada): esos tokens se consumieron igual y viajan
            #     dentro de la excepción, que es un ModelCallError.
            # El __cause__ es para cuando with_retries agotó los intentos y
            # envolvió el error original: el consumo quedó en la excepción
            # encadenada, no en la que llega acá.
            failed_usage = getattr(exc, "usage", None) or getattr(
                exc.__cause__, "usage", None
            )
            span.update(usage_details=failed_usage or {"input": 0, "output": 0, "total": 0})
            raise

        span.update(
            output=doc.text,
            usage_details=doc.usage,
            metadata={"extracted_chars": len(doc.text)},
        )
        return doc


def run_pipeline(
    original_path: str, amendment_path: str, quiet: bool = False
) -> ContractChangeOutput:
    """Ejecuta el pipeline completo: parsing -> Agente 1 -> Agente 2."""
    langfuse = get_client()
    # Lista de un elemento porque _run_stages la completa apenas abre la traza:
    # así tenemos el link incluso si el pipeline falla más adelante.
    trace_url: list[str] = []

    try:
        return _run_stages(langfuse, original_path, amendment_path, quiet, trace_url)
    finally:
        # El flush va en un finally porque si el pipeline falla queremos la
        # traza igual (o más): es la que explica en qué etapa se rompió.
        langfuse.flush()
        if not quiet and trace_url:
            print(f"\nTraza en Langfuse: {trace_url[0]}\n", file=sys.stderr, flush=True)


def _run_stages(
    langfuse, original_path: str, amendment_path: str, quiet: bool, trace_url: list[str]
) -> ContractChangeOutput:
    """Corre las cuatro etapas dentro de la traza y devuelve el resultado validado."""
    with langfuse.start_as_current_observation(
        name="contract-analysis",
        as_type="span",
        input={"original_path": original_path, "amendment_path": amendment_path},
        metadata={
            "pipeline_version": PIPELINE_VERSION,
            "vision_model": VISION_MODEL,
            "agent_model": AGENT_MODEL,
        },
    ) as root_span:
        # La URL se pide con el span raíz activo: Langfuse la arma a partir de
        # la traza en curso. Se captura al principio para tenerla también si
        # alguna etapa falla.
        current_url = langfuse.get_trace_url()
        if current_url:
            trace_url.append(current_url)

        with step(1, "Transcribiendo el contrato original", quiet=quiet):
            original_doc = _traced_parse(langfuse, "parse_original_contract", original_path)

        with step(2, "Transcribiendo la enmienda", quiet=quiet):
            amendment_doc = _traced_parse(langfuse, "parse_amendment_contract", amendment_path)

        with langfuse.start_as_current_observation(
            name="contextualization_agent",
            as_type="generation",
            model=AGENT_MODEL,
            input={"original_text": original_doc.text, "amendment_text": amendment_doc.text},
            metadata={
                "original_chars": len(original_doc.text),
                "amendment_chars": len(amendment_doc.text),
            },
        ) as span:
            with step(3, "Agente 1: mapeando la estructura de ambos documentos", quiet=quiet):
                context_agent = ContextualizationAgent()
                context_result = context_agent.run(original_doc.text, amendment_doc.text)
                context_map = context_result.context_map
                span.update(output=context_map, usage_details=context_result.usage)

        with langfuse.start_as_current_observation(
            name="extraction_agent",
            as_type="generation",
            model=AGENT_MODEL,
            input={"context_map": context_map},
            metadata={"context_map_chars": len(context_map)},
        ) as span:
            with step(4, "Agente 2: identificando y clasificando los cambios", quiet=quiet):
                extraction_agent = ExtractionAgent()
                extraction_result = extraction_agent.run(
                    context_map, original_doc.text, amendment_doc.text
                )
            raw_result = extraction_result.output
            try:
                # Segunda validación explícita: aunque with_structured_output
                # ya fuerza el schema del lado del modelo, tratamos el output
                # del agente como un límite de confianza y lo re-validamos
                # antes de dejarlo salir del pipeline.
                result = ContractChangeOutput.model_validate(raw_result.model_dump())
            except ValidationError as exc:
                span.update(level="ERROR", status_message=str(exc))
                raise
            span.update(
                output=result.model_dump(),
                usage_details=extraction_result.usage,
                metadata={"sections_changed_count": len(result.sections_changed)},
            )

        root_span.update(output=result.model_dump())
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

        result = run_pipeline(args.original_path, args.amendment_path, quiet=args.quiet)
    # El orden de los except importa: Python usa el primero que coincide, y
    # ValidationError de Pydantic es hija de ValueError. Si ValueError fuera
    # primero, un error de validación se reportaría como "Error de entrada".
    except ValidationError as exc:
        print(
            f"El resultado del Agente de Extracción no cumple el schema esperado:\n{exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error de entrada: {exc}", file=sys.stderr)
        sys.exit(1)
    except (RuntimeError, OpenAIError) as exc:
        print(f"Error llamando a la API: {exc}", file=sys.stderr)
        sys.exit(1)

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
