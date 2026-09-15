# Contratos de prueba

Tres pares de contrato original + enmienda en formato JPEG, que cubren
distintos niveles de complejidad. Cada par incluye los cambios reales que
contiene, para poder comparar contra la salida del pipeline.

## Par 1 — Contrato de Servicio SaaS (cambios simples)

`par1_original.jpg` / `par1_enmienda.jpg`

Partes: CloudMetrics Ltd. (Proveedor) y RetailPulse S.A. (Cliente).

La enmienda solo modifica valores dentro de cláusulas que ya existían. No
agrega ni elimina cláusulas.

| Sección | Tipo | Original | Enmienda |
|---|---|---|---|
| 3. Precio | Modificación | USD 1.200 mensuales | USD 1.250 mensuales |
| 4. Disponibilidad del Servicio | Modificación | 99,5% | 99,9% |
| 5. Soporte | Modificación | Correo electrónico | Correo electrónico y sistema de tickets en línea |

Las secciones 1 (Servicio) y 2 (Plazo de Suscripción) no cambian: si el
pipeline las reporta, es un falso positivo.

## Par 2 — Contrato de Licencia de Software (cambios complejos)

`par2_original.jpg` / `par2_enmienda.jpg`

Partes: TechNova S.A. (Licenciante) y DataBridge Soluciones S.R.L. (Licenciatario).

Combina varias modificaciones con una cláusula nueva.

| Sección | Tipo | Original | Enmienda |
|---|---|---|---|
| 1. Otorgamiento de Licencia | Modificación | No exclusiva e intransferible, "fines internos de la empresa" | No exclusiva (se quita "intransferible"), "operaciones internas de negocio" |
| 2. Plazo | Modificación | 12 meses | 24 meses |
| 3. Pago | Modificación | USD 12.000 anuales | USD 15.000 anuales |
| 4. Soporte | Modificación | Correo electrónico | Correo electrónico y chat |
| 5. Terminación | Modificación | Preaviso de 30 días | Preaviso de 60 días |
| 7. Protección de Datos | Adición | — | Cláusula nueva |

La sección 1 es el caso más sutil: el cambio de redacción es menor, pero
quitar "intransferible" tiene impacto legal real. Es un buen caso para ver
si el Agente 2 detecta cambios que no son numéricos.

## Par 3 — Contrato de Servicios de Consultoría (cambios complejos)

`par3_original.jpg` / `par3_enmienda.jpg`

Partes: Orion Consulting Group (Consultor) y GreenWave Energía S.A. (Cliente).

| Sección | Tipo | Original | Enmienda |
|---|---|---|---|
| 1. Alcance del Servicio | Modificación | Expansión de proyectos de energía renovable | Agrega "y análisis regulatorio" |
| 2. Duración | Modificación | 6 meses | 9 meses |
| 3. Honorarios | Modificación | USD 8.000 mensuales | USD 9.500 mensuales |
| 4. Entregables | Modificación | Reportes mensuales | Reportes quincenales |
| 7. Propiedad Intelectual | Adición | — | Cláusula nueva |

Las secciones 5 (Confidencialidad) y 6 (Legislación Aplicable) no cambian.

## Uso

Desde la raíz del proyecto, con el entorno virtual activado:

```bash
python -m src.main data/test_contracts/par1_original.jpg data/test_contracts/par1_enmienda.jpg
python -m src.main data/test_contracts/par2_original.jpg data/test_contracts/par2_enmienda.jpg
python -m src.main data/test_contracts/par3_original.jpg data/test_contracts/par3_enmienda.jpg
```
