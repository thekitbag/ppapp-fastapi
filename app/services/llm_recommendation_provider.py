"""
LLM recommendation provider (SUGGEST-004).

Makes a synchronous HTTP call to an OpenAI-compatible chat completions API
and returns the parsed JSON response. All error conditions raise LLMProviderError
so the engine can fall back cleanly without catching multiple exception types.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a strategic productivity advisor. Your job is to select the single highest-priority
task from the list provided and explain your reasoning in one concise sentence.

Rules:
- You MUST respond with valid JSON only — no prose, no markdown fences.
- Your response MUST match this exact schema:
  {"task_id": "<id from the tasks list>", "score": <integer 0-100>, "why": "<one sentence explanation>"}
- Choose the task that will have the most positive impact on the user's goals right now,
  considering their current energy level and available time.
- "score" represents your confidence that this task is the right choice (100 = certain).
- "why" must be non-empty and explain the selection in plain language the user will understand.
"""


class LLMProviderError(Exception):
    """Raised when the LLM provider call fails for any reason."""


class LLMRecommendationProvider:
    """
    Calls an OpenAI-compatible chat completions endpoint synchronously.

    Parameters are injected from Settings so the provider can be tested with
    a stub or pointed at any compatible API (OpenAI, Azure OpenAI, Ollama, etc.).
    """

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def call(self, context: dict) -> dict:
        """
        POST context to the LLM and return the parsed JSON response dict.

        Raises LLMProviderError on any failure — timeout, HTTP error, bad JSON,
        or unexpected response shape. Callers should catch LLMProviderError and
        fall back to algorithmic ranking.
        """
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context)},
            ],
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise LLMProviderError("LLM request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"LLM API returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.RequestError as exc:
            raise LLMProviderError(f"LLM request failed: {type(exc).__name__}") from exc

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError) as exc:
            raise LLMProviderError("Unexpected LLM response shape") from exc
        except json.JSONDecodeError as exc:
            raise LLMProviderError("LLM returned non-JSON content") from exc
