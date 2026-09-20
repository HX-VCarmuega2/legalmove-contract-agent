"""Modelos que usa cada etapa del pipeline.

Van en código y no en el `.env` porque son una decisión de diseño (los prompts
están ajustados a ellos), y acá en un módulo compartido para que exista una
sola fuente de verdad.
"""
from __future__ import annotations

# Transcribe las imágenes de los contratos.
VISION_MODEL = "gpt-4o"

# Lo usan los dos agentes para razonar sobre los textos.
AGENT_MODEL = "gpt-4o"
