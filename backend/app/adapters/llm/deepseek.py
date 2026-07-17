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
        timeout_seconds: float = 180.0,
        max_transport_attempts: int = 2,
        client: httpx.Client | None = None,
    ) -> None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ProviderConfigurationError("DEEPSEEK_API_KEY is required")
        self._api_key = api_key
        self._model_id = model_id
        self._base_url = base_url.rstrip("/")
        # DeepSeek can acknowledge a large structured-output request quickly,
        # then spend well over 45 seconds generating the response body. Keep
        # connection failures fast while allowing enough time to read it.
        self._timeout = httpx.Timeout(timeout_seconds, connect=15.0)
        self._max_transport_attempts = max(1, max_transport_attempts)
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
        response: httpx.Response | None = None
        for attempt in range(self._max_transport_attempts):
            try:
                response = self._client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=request_body,
                    timeout=self._timeout,
                )
                break
            except httpx.TransportError:
                if attempt + 1 >= self._max_transport_attempts:
                    raise
        assert response is not None
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

