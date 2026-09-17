# LegalMove — Agente Autónomo de Comparación de Contratos

Proyecto Integrador del Módulo 4 de AI Engineering (Henry).

Sistema multi-agente que recibe las imágenes escaneadas de un contrato
original y de su enmienda, extrae el texto con GPT-4o Vision y, mediante dos
agentes especializados, identifica y resume los cambios legales. La salida es
un JSON validado con Pydantic y cada etapa queda registrada en Langfuse.

## Problema y objetivo

El equipo de Compliance de LegalMove dedica más de 40 horas semanales a
comparar manualmente contratos con sus enmiendas. El cuello de botella no está
en redactar el resumen, sino en que un abogado tenga que abrir los dos
documentos y compararlos cláusula por cláusula para recién entonces decidir qué
hacer con ese contrato.

El objetivo del sistema, entonces, no es "resumir cambios": es **derivar y
priorizar contratos sin que una persona tenga que leer ambos documentos**. Cada
campo de la salida sirve a una decisión distinta:

| Campo | Para qué se usa |
|---|---|
| `topics_touched` | **Derivación.** Si toca protección de datos va al especialista en privacidad; si toca condiciones de pago, a finanzas |
| `sections_changed` | **Foco.** Le dice al abogado qué cláusulas revisar, en vez de leer el contrato entero |
| `summary_of_the_change` | **Contexto y prioridad.** No es lo mismo una tarifa que sube 50 dólares que una cláusula de confidencialidad que desaparece |

Dos consecuencias de este encuadre, que explican varias decisiones de diseño:

- **El sistema no reemplaza al abogado, hace el triage.** Decidir de forma
  autónoma sobre contratos sería inaceptable en un contexto legal, donde un
  error tiene consecuencias contractuales reales. El valor está en que la
  persona llegue a la revisión sabiendo dónde mirar.
- **No perderse un cambio es más importante que redactar un resumen elegante.**
  Si el sistema omite una cláusula, nadie la revisa y el error llega a
  producción. Si el resumen es incompleto pero la cláusula está marcada, el
  abogado la abre igual y lo detecta. Por eso las pruebas ponen tanto peso en
  los falsos negativos y en los falsos positivos a nivel de sección.

## Arquitectura

```mermaid
flowchart TD
    A["Imagen<br/>contrato original"] --> P1["parse_contract_image()<br/>GPT-4o Vision"]
    B["Imagen<br/>enmienda"] --> P2["parse_contract_image()<br/>GPT-4o Vision"]

    P1 -->|texto original| C1["ContextualizationAgent<br/>Analista Legal Senior"]
    P2 -->|texto enmienda| C1

    C1 -->|mapa de contexto| C2["ExtractionAgent<br/>Auditor Legal"]
    P1 -->|texto original| C2
    P2 -->|texto enmienda| C2

    C2 -->|structured output| V["Validación Pydantic<br/>ContractChangeOutput"]
    V --> O["JSON final"]
```

El pipeline tiene cuatro etapas:

1. **Parsing multimodal.** `parse_contract_image()` codifica cada imagen en
   base64 y le pide a GPT-4o que transcriba el contrato de forma fiel,
   conservando la numeración de las cláusulas. Se ejecuta dos veces: una por
   documento.
2. **Agente 1: contextualización.** Recibe los dos textos y arma un mapa de
   correspondencia: qué secciones existen en cada documento, cuál se
   corresponde con cuál y cuáles aparecen solo en uno de los dos. No detecta
   cambios.
3. **Agente 2: extracción.** Recibe el mapa del Agente 1 junto con los dos
   textos completos, identifica cada cambio y lo clasifica como adición,
   eliminación o modificación. Devuelve directamente un `ContractChangeOutput`.
4. **Validación.** El resultado se valida de nuevo con Pydantic antes de salir
   del pipeline.

### Por qué dos agentes

Comparar dos contratos implica resolver dos problemas distintos: **alinear**
las secciones (qué cláusula de la enmienda corresponde a cuál del original) y
**comparar el contenido** de cada par ya alineado. Si un solo prompt resuelve
ambos, un error de alineación se convierte directamente en un cambio inventado
o en uno omitido, y no hay forma de saber cuál de las dos tareas falló.

Separarlos da tres ventajas:

- Cada agente tiene un system prompt con un rol y una responsabilidad únicos,
  y se le prohíbe explícitamente hacer el trabajo del otro.
- El mapa del Agente 1 queda registrado en Langfuse, así que ante un resultado
  incorrecto se puede ver si falló la alineación o la comparación.
- El Agente 2 recibe el mapa **y** los textos completos: el mapa le indica
  dónde mirar y los textos le dan la redacción exacta para detectar cambios
  de montos, plazos o palabras.

## Estructura del repositorio

```
legalmove-contract-agent/
├── src/
│   ├── main.py                       # Entry point, orquestación y spans de Langfuse
│   ├── image_parser.py               # Validación, encoding base64 y llamada a GPT-4o Vision
│   ├── models.py                     # ContractChangeOutput (Pydantic)
│   ├── retry.py                      # Reintentos ante errores transitorios de la API
│   └── agents/
│       ├── contextualization_agent.py   # Agente 1
│       ├── extraction_agent.py          # Agente 2
│       └── results.py                   # Tipos de retorno de los agentes (resultado + tokens)
├── data/
│   └── test_contracts/               # 3 pares de contratos de prueba + README
├── evals/
│   ├── cases.py                      # Casos de evaluación de precisión
│   └── run_evals.py                  # Runner de las evaluaciones
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

Requisitos: Python 3.10 o superior (desarrollado con 3.13), una API key de OpenAI con acceso a
GPT-4o y una cuenta en [Langfuse Cloud](https://cloud.langfuse.com).

**1. Clonar el repositorio**

```bash
git clone <url-del-repositorio>
cd legalmove-contract-agent
```

**2. Crear y activar el entorno virtual**

```bash
python -m venv .venv

# Git Bash (Windows)
source .venv/Scripts/activate

# PowerShell (Windows)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

**3. Instalar dependencias**

```bash
pip install -r requirements.txt
```

**4. Configurar variables de entorno**

```bash
cp .env.example .env
```

Completar `.env` con las claves reales:

| Variable | Dónde se obtiene |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `LANGFUSE_PUBLIC_KEY` | Langfuse → Settings → API Keys |
| `LANGFUSE_SECRET_KEY` | Langfuse → Settings → API Keys |
| `LANGFUSE_HOST` | Depende de la región del proyecto (ver nota) |

> **Nota sobre `LANGFUSE_HOST`:** Langfuse Cloud tiene dos regiones con hosts
> distintos: `https://cloud.langfuse.com` (EU) y `https://us.cloud.langfuse.com`
> (US). Si el host no coincide con la región del proyecto, la exportación de
> trazas falla con `401 Unauthorized` aunque las claves sean correctas.

## Uso

Desde la raíz del proyecto, con el entorno virtual activado. Las dos formas son
equivalentes:

```bash
python src/main.py <imagen_original> <imagen_enmienda>
python -m src.main <imagen_original> <imagen_enmienda>
```

Ejemplo con el Par 1 de prueba:

```bash
python src/main.py data/test_contracts/par1_original.jpg data/test_contracts/par1_enmienda.jpg
```

Salida:

```json
{
  "sections_changed": [
    "3. Precio",
    "4. Disponibilidad del Servicio",
    "5. Soporte"
  ],
  "topics_touched": [
    "condiciones de pago",
    "nivel de servicio",
    "soporte al cliente"
  ],
  "summary_of_the_change": "La enmienda introduce tres cambios principales: 1) El precio mensual que el Cliente debe pagar se incrementó de USD 1.200 a USD 1.250. 2) El nivel de disponibilidad del servicio garantizado por el Proveedor aumentó de 99,5% a 99,9%. 3) Se amplió el canal de soporte al cliente, que ahora incluye no solo correo electrónico sino también un sistema de tickets en línea."
}
```

Ver [data/test_contracts/README.md](data/test_contracts/README.md) para los
tres pares disponibles y los cambios esperados en cada uno.

## Modelo de salida

```python
class ContractChangeOutput(BaseModel):
    sections_changed: list[str]      # Secciones modificadas, agregadas o eliminadas
    topics_touched: list[str]        # Categorías legales o comerciales afectadas
    summary_of_the_change: str       # Descripción detallada de los cambios
```

Los tres campos son obligatorios y no aceptan valores vacíos (`min_length=1`).
Cada campo tiene una `description` que se envía al modelo como parte del JSON
schema, de modo que funciona también como instrucción de qué completar.

## Trazabilidad con Langfuse

Cada ejecución genera una traza con esta jerarquía:

```
contract-analysis                  (span raíz: paths de entrada y JSON final)
├── parse_original_contract        (generation: path, texto extraído, tokens)
├── parse_amendment_contract       (generation: path, texto extraído, tokens)
├── contextualization_agent        (generation: ambos textos, mapa de contexto)
└── extraction_agent               (generation: mapa de contexto, JSON validado)
```

Para cada etapa quedan registrados el input, el output, la latencia, el consumo
de tokens y el costo, siempre con los tokens reales que informa la API (en los
agentes se obtienen del `usage_metadata` de LangChain, y en el caso del Agente 2
hace falta pedir la respuesta cruda con `include_raw=True`, porque la salida
estructurada por sí sola no la expone). Si la validación Pydantic falla, el span
`extraction_agent` queda marcado con nivel `ERROR` y el detalle del error.

Cada span incluye además metadata para debugging: la versión del pipeline y los
modelos usados en la raíz, el nombre y el tamaño del archivo en los spans de
parsing, y el tamaño de los textos y del mapa de contexto en los de los agentes.

Si una etapa necesitó reintentos, su span queda marcado con nivel `WARNING` y
con la cantidad, el motivo y los tokens desperdiciados (`wasted_tokens`) en la
metadata. Sin eso, un reintento solo se notaría como "esta etapa tardó más de lo
normal".

Los tokens de un intento fallido se consumen igual, así que la excepción los
transporta para poder sumarlos. No todos los errores gastan tokens: un rate
limit o un timeout no llegan a generar respuesta, mientras que una negativa del
modelo sí se paga. Esos tokens quedan registrados en la metadata pero **no** se
suman al costo que calcula Langfuse, que refleja únicamente el intento exitoso;
`wasted_tokens` es lo que permite explicar esa diferencia frente a la factura de
OpenAI.

Con esto, ante cualquier resultado se puede reconstruir el camino completo:
qué texto leyó el OCR, qué mapa armó el Agente 1 y con qué información decidió
el Agente 2.

## Manejo de errores

| Situación | Comportamiento |
|---|---|
| Falta `OPENAI_API_KEY` | Falla antes de llamar a la API, con un mensaje que indica configurar `.env` |
| La imagen no existe | Falla antes de llamar a la API: `Error de entrada: No se encontró la imagen` |
| Extensión no soportada | Falla antes de llamar a la API; solo acepta `.jpg`, `.jpeg` y `.png` |
| Archivo vacío, corrupto o renombrado | Se valida por *magic bytes* que el contenido corresponda a la extensión, antes de llamar a la API |
| Rate limit, timeout, error 5xx o de conexión | Reintenta hasta 3 veces con espera creciente (2 s, 4 s) |
| API key inválida o request mal formado | Falla sin reintentar, porque reintentar no cambiaría el resultado |
| Transcripción truncada por límite de tokens | Falla en vez de devolverla (`finish_reason == "length"`) |
| El modelo se niega a transcribir | Se detecta por un texto sospechosamente corto (menos de 80 caracteres) y se reintenta, porque es intermitente |
| Respuesta del Agente 2 truncada o no parseable | Falla con un mensaje explícito en vez de propagar un valor vacío |
| El JSON no cumple el schema | Error de validación con el detalle de Pydantic |

En todos los casos el programa termina con código de salida `1` y un mensaje
legible en lugar de un traceback.

Los dos casos de truncamiento merecen una aclaración, porque no son
defensivos por gusto: si una transcripción se corta a la mitad y se devuelve
igual, los agentes comparan contra un contrato incompleto y reportan como
**eliminadas** cláusulas que en realidad nunca se transcribieron. Es preferible
fallar a entregar un falso positivo de ese tipo.

El chequeo de "respuesta sospechosamente corta" surgió de un caso real durante
el desarrollo: al probar el límite de tokens, el modelo no truncó la respuesta
sino que contestó *"Lo siento, no puedo ayudar con eso"*. Como esa respuesta
termina normalmente, `finish_reason` no la detecta y ese texto se habría
devuelto como si fuera el contrato: el sistema habría reportado que la enmienda
eliminó todas las cláusulas.

Más tarde apareció la misma negativa en una corrida normal, sin límite de
tokens: sobre la misma imagen, 2 de cada 3 intentos funcionan y 1 falla. Por eso
se trata como un error transitorio y se reintenta. El criterio para decidir qué
se reintenta y qué no es siempre el mismo: **¿un reintento puede dar un
resultado distinto?** Con una negativa intermitente o un rate limit, sí; con una
API key inválida o una respuesta truncada por el límite de tokens, no.

## Evaluación de precisión

Los contratos de prueba cubren modificaciones de valores y cláusulas nuevas,
pero no otras situaciones que el sistema debe manejar. La carpeta `evals/`
contiene seis casos escritos a mano, en texto plano, que prueban el
razonamiento de los agentes sin pasar por el OCR:

| Caso | Qué prueba |
|---|---|
| `eliminacion_clausula` | Una cláusula que desaparece en la enmienda |
| `palabra_eliminada` | Se quita una sola palabra que cambia el alcance de una obligación |
| `clausula_renombrada` | Cambia el título y el contenido queda igual |
| `renombrada_y_modificada` | Cambian el título y el contenido a la vez |
| `renumeracion` | Se inserta una cláusula y las siguientes cambian de número |
| `cambios_multiples_en_clausula` | Dos cambios dentro de la misma cláusula |

Todos parten del mismo acuerdo de confidencialidad y cada uno introduce **un
solo tipo de cambio**, para que un caso que falla identifique exactamente qué
situación no se maneja bien.

```bash
python -m evals.run_evals                              # todos los casos
python -m evals.run_evals renumeracion --repeat 3      # un caso, tres veces
python -m evals.run_evals --show-context               # muestra el mapa del Agente 1
```

Como la salida de un modelo varía entre ejecuciones, los chequeos no comparan
contra un texto exacto: verifican que aparezcan las palabras clave que
corresponden y que **no** se listen como cambiadas las secciones que no
cambiaron. La opción `--repeat` existe porque una corrida exitosa no prueba
nada: interesa saber si un caso pasa 3 de 3 o 1 de 3. Los chequeos automáticos
son una red mínima, así que cada caso imprime también qué debería reportar el
sistema, para revisarlo a mano.

## Decisiones técnicas

**GPT-4o Vision en lugar de OCR tradicional.** El objetivo no es solo leer
caracteres, sino conservar la estructura del documento (títulos, numeración de
cláusulas) que los agentes necesitan para alinear secciones. El prompt de
parsing prohíbe resumir o interpretar: esa etapa solo transcribe.

**`detail: "high"` y `temperature=0` en el parsing.** Los contratos son texto
denso, donde un dígito mal leído cambia el sentido de una cláusula. La
resolución alta mejora la lectura y la temperatura cero reduce la variación
entre ejecuciones.

**Cliente de OpenAI para el parsing, LangChain para los agentes.** El parsing
es una única llamada multimodal y no necesita una capa adicional. En los
agentes, LangChain aporta `with_structured_output()`, que convierte el modelo
Pydantic en JSON schema y devuelve el objeto ya parseado.

**Structured outputs más validación explícita.** `with_structured_output()` ya
obliga al modelo a respetar el schema, pero el resultado se valida otra vez con
`ContractChangeOutput.model_validate()` antes de salir del pipeline. La salida
de un modelo se trata como un dato no confiable hasta validarla.

**Prompts con verificación de evidencia.** Durante el desarrollo, una ejecución
del Par 1 reportó una cláusula de "Renovación Automática" que no existe en
ninguno de los dos documentos. El texto del OCR era correcto, así que el error
venía del razonamiento de los agentes. Se agregó a ambos prompts una regla que
exige poder señalar la evidencia textual de cada cambio antes de reportarlo.

**Validación temprana.** Las variables de entorno y los archivos se validan
antes de instanciar los agentes, para que un error de configuración falle
rápido y con un mensaje claro.

**Dependencias inyectables.** Tanto `parse_contract_image()` como los dos
agentes reciben su cliente (o su modelo) como parámetro opcional, y solo crean
uno real si no se lo pasan. Eso permite probar caminos difíciles de provocar
contra la API real: por ejemplo, el manejo de una transcripción truncada se
verifica pasando un cliente falso que devuelve `finish_reason="length"`, sin
gastar una llamada ni depender de cómo reaccione el modelo.

**Versiones fijadas en `requirements.txt`.** Garantiza que el proyecto instale
exactamente las mismas versiones en cualquier máquina.

## Limitaciones conocidas

- **No determinismo.** Aun con `temperature=0`, GPT-4o puede devolver
  resultados distintos en dos ejecuciones con la misma entrada. La regla de
  verificación de evidencia reduce las alucinaciones, pero no las elimina.
- **Completitud del resumen bajo muchos cambios.** Cuando una enmienda modifica
  muchas cláusulas a la vez, el resumen puede omitir algún matiz. El caso
  medido es el Par 2: la cláusula 1 quita las palabras "intransferible" y
  "únicamente" además de reescribir el propósito de la licencia, y el resumen
  no siempre menciona las tres cosas. El OCR transcribe el texto correctamente
  y la sección **siempre** aparece en `sections_changed`, así que la derivación
  funciona: lo que falla es la completitud del resumen, no la detección.
  Las evaluaciones con una sola cláusula modificada pasan de forma consistente,
  lo que indica que el problema aparece por volumen de cambios.
  La mejora pendiente sería que el Agente 1 marque en su mapa qué pares de
  cláusulas difieren textualmente, para que el Agente 2 llegue con menos
  trabajo; se descartó por ahora para no mezclar las responsabilidades de los
  dos agentes.
- **Un solo formato de entrada.** El sistema acepta imágenes JPEG y PNG de una
  página; no procesa PDFs ni documentos de varias páginas.
- **Contratos de una sola llamada.** Un contrato muy extenso puede no entrar en
  la ventana de contexto de una sola llamada. El sistema lo detecta y falla con
  un mensaje claro, pero no lo resuelve dividiendo el documento.
