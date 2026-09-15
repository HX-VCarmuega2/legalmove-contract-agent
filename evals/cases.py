"""Casos de evaluación para medir la precisión de los agentes.

Todos los casos parten del mismo acuerdo de confidencialidad, y cada enmienda
introduce UN solo tipo de cambio: si un caso falla, se sabe exactamente qué
situación no maneja el sistema. Los textos están escritos a mano (sin
imágenes) porque lo que se evalúa es el razonamiento de los agentes, no el OCR.
"""
from __future__ import annotations

from dataclasses import dataclass

# (número, título, texto)
Clause = tuple[str, str, str]

_PARTES = (
    'entre Andes Biotech S.A. ("Parte Reveladora") y '
    'Norte Data S.R.L. ("Parte Receptora")'
)

OBJETO = (
    "La Parte Reveladora compartirá información técnica y comercial relacionada "
    "con el desarrollo de nuevos productos farmacéuticos."
)
OBLIGACIONES = (
    "La Parte Receptora se compromete a no divulgar la información confidencial "
    "a terceros y a utilizarla exclusivamente para evaluar una posible alianza comercial."
)
ALCANCE = "Las obligaciones de este acuerdo rigen en el territorio de la República Argentina."
RESTRICCION = (
    "La Parte Receptora no podrá utilizar la información confidencial para "
    "desarrollar productos que compitan con los de la Parte Reveladora."
)
PLAZO = "Este acuerdo tendrá una vigencia de 2 años desde la fecha de firma."
JURISDICCION = (
    "Cualquier controversia será resuelta por los tribunales ordinarios de la "
    "Ciudad Autónoma de Buenos Aires."
)

ORIGINAL_CLAUSES: list[Clause] = [
    ("1", "Objeto", OBJETO),
    ("2", "Obligaciones de la Parte Receptora", OBLIGACIONES),
    ("3", "Alcance Territorial", ALCANCE),
    ("4", "Restricción de Uso", RESTRICCION),
    ("5", "Plazo", PLAZO),
    ("6", "Jurisdicción", JURISDICCION),
]


def _render(title: str, intro: str, clauses: list[Clause]) -> str:
    """Arma el texto con el mismo formato Markdown que devuelve el parser de imágenes."""
    body = "\n\n".join(f"{number}. {clause_title}\n{text}" for number, clause_title, text in clauses)
    return f"## {title}\n\n{intro}\n\n{body}"


ORIGINAL_TEXT = _render(
    "ACUERDO DE CONFIDENCIALIDAD",
    f"Este acuerdo se celebra el 5 de marzo de 2024 {_PARTES}.",
    ORIGINAL_CLAUSES,
)


def render_amendment(clauses: list[Clause]) -> str:
    return _render(
        "ACUERDO DE CONFIDENCIALIDAD – ENMIENDA",
        f"La presente enmienda modifica el acuerdo celebrado el 5 de marzo de 2024 {_PARTES}.",
        clauses,
    )


@dataclass
class EvalCase:
    name: str
    change: str  # qué cambio introduce la enmienda
    expected: str  # qué debería reportar el sistema (para revisión manual)
    amendment_clauses: list[Clause]
    must_mention: list[str]  # deben aparecer en sections_changed o en el resumen
    must_not_list_sections: list[str]  # no deben aparecer en sections_changed (falsos positivos)


CASES: list[EvalCase] = [
    EvalCase(
        name="eliminacion_clausula",
        change="Se elimina la cláusula 4 (Restricción de Uso). El resto conserva su número.",
        expected="Una ELIMINACIÓN de la cláusula 4. Ninguna otra cláusula cambió.",
        amendment_clauses=[
            ("1", "Objeto", OBJETO),
            ("2", "Obligaciones de la Parte Receptora", OBLIGACIONES),
            ("3", "Alcance Territorial", ALCANCE),
            ("5", "Plazo", PLAZO),
            ("6", "Jurisdicción", JURISDICCION),
        ],
        must_mention=["restricción de uso", "elimin"],
        must_not_list_sections=["objeto", "obligaciones", "alcance", "plazo", "jurisdicción"],
    ),
    EvalCase(
        name="palabra_eliminada",
        change='En la cláusula 2 se quita la palabra "exclusivamente". Nada más cambia.',
        expected=(
            'Una MODIFICACIÓN de la cláusula 2 que mencione que se quitó "exclusivamente", '
            "lo que amplía los usos permitidos de la información."
        ),
        amendment_clauses=[
            ("1", "Objeto", OBJETO),
            (
                "2",
                "Obligaciones de la Parte Receptora",
                "La Parte Receptora se compromete a no divulgar la información confidencial "
                "a terceros y a utilizarla para evaluar una posible alianza comercial.",
            ),
            ("3", "Alcance Territorial", ALCANCE),
            ("4", "Restricción de Uso", RESTRICCION),
            ("5", "Plazo", PLAZO),
            ("6", "Jurisdicción", JURISDICCION),
        ],
        must_mention=["exclusivamente"],
        must_not_list_sections=["objeto", "alcance", "restricción", "plazo", "jurisdicción"],
    ),
    EvalCase(
        name="clausula_renombrada",
        change='La cláusula 6 cambia su título de "Jurisdicción" a "Resolución de Controversias". El texto es idéntico.',
        expected=(
            "Una MODIFICACIÓN del título de la cláusula 6, aclarando que el contenido no cambió. "
            "NO debe reportarse como una eliminación más una adición."
        ),
        amendment_clauses=[
            ("1", "Objeto", OBJETO),
            ("2", "Obligaciones de la Parte Receptora", OBLIGACIONES),
            ("3", "Alcance Territorial", ALCANCE),
            ("4", "Restricción de Uso", RESTRICCION),
            ("5", "Plazo", PLAZO),
            ("6", "Resolución de Controversias", JURISDICCION),
        ],
        must_mention=["resolución de controversias"],
        must_not_list_sections=["objeto", "obligaciones", "alcance", "restricción", "plazo"],
    ),
    EvalCase(
        name="renombrada_y_modificada",
        change=(
            'La cláusula 3 pasa de "Alcance Territorial" a "Ámbito de Aplicación" y '
            "extiende el territorio a Chile y Uruguay."
        ),
        expected=(
            "Una sola MODIFICACIÓN de la cláusula 3 (título y territorio). "
            "NO debe reportarse como una eliminación más una adición."
        ),
        amendment_clauses=[
            ("1", "Objeto", OBJETO),
            ("2", "Obligaciones de la Parte Receptora", OBLIGACIONES),
            (
                "3",
                "Ámbito de Aplicación",
                "Las obligaciones de este acuerdo rigen en los territorios de la República "
                "Argentina, la República de Chile y la República Oriental del Uruguay.",
            ),
            ("4", "Restricción de Uso", RESTRICCION),
            ("5", "Plazo", PLAZO),
            ("6", "Jurisdicción", JURISDICCION),
        ],
        must_mention=["chile", "uruguay"],
        must_not_list_sections=["objeto", "obligaciones", "restricción", "plazo", "jurisdicción"],
    ),
    EvalCase(
        name="renumeracion",
        change=(
            'Se inserta una cláusula nueva 3 ("Devolución de la Información"). Las cláusulas '
            "siguientes pasan a ser 4, 5, 6 y 7, con el mismo título y texto."
        ),
        expected=(
            "Una sola ADICIÓN (la nueva cláusula 3). Las cláusulas renumeradas no cambiaron "
            "su contenido y no deben listarse como modificadas (a lo sumo, el resumen puede "
            "mencionar la renumeración)."
        ),
        amendment_clauses=[
            ("1", "Objeto", OBJETO),
            ("2", "Obligaciones de la Parte Receptora", OBLIGACIONES),
            (
                "3",
                "Devolución de la Información",
                "Al finalizar el acuerdo, la Parte Receptora deberá devolver o destruir "
                "toda la información confidencial recibida.",
            ),
            ("4", "Alcance Territorial", ALCANCE),
            ("5", "Restricción de Uso", RESTRICCION),
            ("6", "Plazo", PLAZO),
            ("7", "Jurisdicción", JURISDICCION),
        ],
        must_mention=["devolución"],
        must_not_list_sections=["objeto", "obligaciones", "alcance", "restricción", "plazo", "jurisdicción"],
    ),
    EvalCase(
        name="cambios_multiples_en_clausula",
        change=(
            'En la cláusula 2 se quita "exclusivamente" y además se reescribe el propósito: '
            '"evaluar una posible alianza comercial" pasa a "analizar oportunidades de '
            'colaboración entre las partes". Reproduce el patrón del Par 2 ("intransferible").'
        ),
        expected=(
            "Una MODIFICACIÓN de la cláusula 2 cuyo resumen mencione LOS DOS cambios: el nuevo "
            'propósito y que se quitó "exclusivamente".'
        ),
        amendment_clauses=[
            ("1", "Objeto", OBJETO),
            (
                "2",
                "Obligaciones de la Parte Receptora",
                "La Parte Receptora se compromete a no divulgar la información confidencial "
                "a terceros y a utilizarla para analizar oportunidades de colaboración entre las partes.",
            ),
            ("3", "Alcance Territorial", ALCANCE),
            ("4", "Restricción de Uso", RESTRICCION),
            ("5", "Plazo", PLAZO),
            ("6", "Jurisdicción", JURISDICCION),
        ],
        must_mention=["exclusivamente", "colaboración"],
        must_not_list_sections=["objeto", "alcance", "restricción", "plazo", "jurisdicción"],
    ),
]
