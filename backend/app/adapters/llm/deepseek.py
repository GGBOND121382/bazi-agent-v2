"""DeepSeek structured-output adapter with environment-only secret injection."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class ProviderConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    payload: dict[str, Any]
    model_id: str
    prompt_version: str


class StructuredOutputProvider(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
        schema: dict[str, Any],
        prompt_version: str,
    ) -> ProviderResponse: ...


class DeepSeekProvider:
    """Thin provider boundary; never logs or returns the API key/raw response."""

    def __init__(
        self,
        *,
        model_id: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout_seconds: float = 45.0,
        client: httpx.Client | None = None,
    ) -> None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ProviderConfigurationError("DEEPSEEK_API_KEY is required")
        self._api_key = api_key
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client or httpx.Client()

    def complete_json(
        self,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
        schema: dict[str, Any],
        prompt_version: str,
    ) -> ProviderResponse:
        request_body = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"input": input_payload, "required_schema": schema},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=request_body,
            timeout=self._timeout,
        )
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
            payload = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("provider returned invalid structured output") from exc
        if not isinstance(payload, dict):
            raise ValueError("provider structured output must be an object")
        return ProviderResponse(
            payload=payload,
            model_id=self._model_id,
            prompt_version=prompt_version,
        )

