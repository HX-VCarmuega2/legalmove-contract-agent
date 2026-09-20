"""Corre los casos de evaluación contra los dos agentes.

Uso (desde la raíz del proyecto):
    python -m evals.run_evals                           # todos los casos
    python -m evals.run_evals renumeracion              # uno o más casos puntuales
    python -m evals.run_evals --show-context            # muestra también el mapa del Agente 1
    python -m evals.run_evals --repeat 3                # corre cada caso 3 veces

Los chequeos automáticos son una red mínima: verifican palabras clave, no la
calidad completa de la respuesta. Por eso cada caso imprime también qué
debería reportar el sistema, para revisarlo a mano.
"""
from __future__ import annotations

import argparse
import sys
import unicodedata

from dotenv import load_dotenv

load_dotenv()

# La consola de Windows suele usar cp1252 y no puede imprimir "→" ni algunos
# acentos que aparecen en los resultados.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

from evals.cases import CASES, ORIGINAL_TEXT, EvalCase, render_amendment
from src.agents.contextualization_agent import ContextualizationAgent
from src.agents.extraction_agent import ExtractionAgent
from src.models import ContractChangeOutput


def normalize(text: str) -> str:
    """Pasa a minúsculas y quita tildes, para que "Jurisdicción" coincida con "jurisdiccion"."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def check_case(case: EvalCase, result: ContractChangeOutput) -> list[tuple[str, bool]]:
    sections = normalize(" | ".join(result.sections_changed))
    everything = sections + " " + normalize(result.summary_of_the_change)

    checks = [(f'menciona "{keyword}"', normalize(keyword) in everything) for keyword in case.must_mention]
    checks += [
        (f'no lista "{keyword}" como sección cambiada', normalize(keyword) not in sections)
        for keyword in case.must_not_list_sections
    ]
    if case.expect_empty:
        checks.append(("sections_changed viene vacía", len(result.sections_changed) == 0))
        checks.append(("topics_touched viene vacía", len(result.topics_touched) == 0))
    return checks


def run_once(
    case: EvalCase,
    context_agent: ContextualizationAgent,
    extraction_agent: ExtractionAgent,
    show_context: bool,
) -> bool:
    """Corre un caso una vez, imprime el resultado y devuelve si pasó todos los chequeos."""
    amendment_text = render_amendment(case.amendment_clauses)
    try:
        context_map = context_agent.run(ORIGINAL_TEXT, amendment_text).context_map
        result = extraction_agent.run(context_map, ORIGINAL_TEXT, amendment_text).output
    except Exception as exc:
        print(f"ERROR al correr el caso: {exc}")
        return False

    if show_context:
        print("Mapa del Agente 1:")
        print(context_map)
        print("-" * 80)

    print(f"sections_changed: {result.sections_changed}")
    print(f"summary: {result.summary_of_the_change}")
    print("-" * 80)

    checks = check_case(case, result)
    for description, ok in checks:
        print(f"  [{'OK' if ok else 'FALLA'}] {description}")
    return all(ok for _, ok in checks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Corre los casos de evaluación de los agentes.")
    parser.add_argument("cases", nargs="*", help="Nombres de los casos a correr (por defecto, todos)")
    parser.add_argument("--show-context", action="store_true", help="Imprime el mapa del Agente 1")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Cantidad de corridas por caso, para medir la consistencia (por defecto, 1)",
    )
    args = parser.parse_args()

    selected = [case for case in CASES if not args.cases or case.name in args.cases]
    unknown = set(args.cases) - {case.name for case in CASES}
    if unknown:
        parser.error(f"Casos inexistentes: {', '.join(sorted(unknown))}")

    context_agent = ContextualizationAgent()
    extraction_agent = ExtractionAgent()
    passes_by_case: dict[str, int] = {}

    for case in selected:
        print("=" * 80)
        print(f"CASO: {case.name}")
        print(f"Cambio:   {case.change}")
        print(f"Esperado: {case.expected}")

        passes = 0
        for attempt in range(1, args.repeat + 1):
            print("-" * 80)
            print(f"Corrida {attempt}/{args.repeat}")
            if run_once(case, context_agent, extraction_agent, args.show_context):
                passes += 1
        passes_by_case[case.name] = passes

    print("=" * 80)
    print("RESUMEN (corridas que pasaron todos los chequeos automáticos)")
    for name, passes in passes_by_case.items():
        print(f"  {name:<32} {passes}/{args.repeat}")


if __name__ == "__main__":
    main()
