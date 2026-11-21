"""Klient LLM zgodny z OpenAI API (OpenRouter, Mistral API, vLLM, Ollama...)."""

import json
import logging
import re
from functools import lru_cache

from openai import BadRequestError, OpenAI

from app.config import get_settings

log = logging.getLogger(__name__)


@lru_cache
def _client() -> OpenAI:
    s = get_settings()
    return OpenAI(base_url=s.llm_base_url, api_key=s.llm_api_key or "none", max_retries=s.llm_max_retries)


_schema_unsupported = False  # zapamiętane po pierwszym odrzuceniu json_schema przez API


def _parse(content: str) -> dict:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)  # model dopisał tekst wokół JSON-a
        return json.loads(m.group(0)) if m else {}


def _call(system: str, user: str, response_format: dict) -> str:
    s = get_settings()
    resp = _client().chat.completions.create(
        model=s.llm_model,
        temperature=s.llm_temperature,
        response_format=response_format,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return resp.choices[0].message.content or "{}"


def complete_json(system: str, user: str, json_schema: dict | None = None) -> dict:
    """Zwraca odpowiedź modelu jako dict.

    Ze schematem próbuje structured outputs; jeśli model ich nie obsługuje,
    dokleja schemat do promptu i używa trybu json_object.
    """
    global _schema_unsupported
    use_schema = json_schema and get_settings().llm_structured_output and not _schema_unsupported
    if use_schema:
        try:
            fmt = {"type": "json_schema", "json_schema": {"name": "output", "schema": json_schema, "strict": True}}
            return _parse(_call(system, user, fmt))
        except BadRequestError as e:
            log.warning("Model nie obsługuje json_schema, przełączam na json_object: %s", e)
            _schema_unsupported = True
    if json_schema:
        user += "\n\nZwróć wyłącznie JSON zgodny z JSON Schema:\n" + json.dumps(json_schema, ensure_ascii=False)
    return _parse(_call(system, user, {"type": "json_object"}))
