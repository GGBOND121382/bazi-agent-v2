"""DeepSeek streaming structured-output adapter with environment-only secrets."""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

StreamEventCallback = Callable[[dict[str, Any]], None]


class ModelProviderError(RuntimeError):
    """Safe provider failure that can be mapped to a public job error code."""

    error_code = "MODEL_PROVIDER_ERROR"
    retryable = True


class ProviderConfigurationError(ModelProviderError):
    error_code = "MODEL_CONFIGURATION_ERROR"
    retryable = False


class ModelTimeoutError(ModelProviderError):
    error_code = "MODEL_TIMEOUT"


class ModelStreamInterruptedError(ModelProviderError):
    error_code = "MODEL_STREAM_INTERRUPTED"


class ModelOutputTruncatedError(ModelProviderError):
    error_code = "MODEL_OUTPUT_TRUNCATED"
    retryable = False


class ModelInvalidOutputError(ModelProviderError):
    error_code = "MODEL_INVALID_OUTPUT"
    retryable = False


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    payload: dict[str, Any]
    model_id: str
    prompt_version: str
    reasoning_content: str = ""
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None
    streamed: bool = False
    transport_attempts: int = 1
    timings: dict[str, float] = field(default_factory=dict)


class StructuredOutputProvider(Protocol):
    def complete_json(
        self,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
        schema: dict[str, Any],
        prompt_version: str,
        on_stream_event: StreamEventCallback | None = None,
    ) -> ProviderResponse: ...


class DeepSeekProvider:
    """Stream one coherent analysis and aggregate it before JSON validation."""

    def __init__(
        self,
        *,
        model_id: str | None = None,
        base_url: str | None = None,
        read_timeout_seconds: float | None = None,
        total_timeout_seconds: float | None = None,
        max_transport_attempts: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise ProviderConfigurationError("DEEPSEEK_API_KEY is required")
        self._api_key = api_key
        self._model_id = model_id or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
        self._base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        read_timeout = read_timeout_seconds or float(os.environ.get("DEEPSEEK_STREAM_IDLE_TIMEOUT", "90"))
        self._total_timeout_seconds = total_timeout_seconds or float(
            os.environ.get("DEEPSEEK_TOTAL_TIMEOUT", "600")
        )
        self._timeout = httpx.Timeout(
            connect=float(os.environ.get("DEEPSEEK_CONNECT_TIMEOUT", "15")),
            write=float(os.environ.get("DEEPSEEK_WRITE_TIMEOUT", "60")),
            read=read_timeout,
            pool=float(os.environ.get("DEEPSEEK_POOL_TIMEOUT", "30")),
        )
        configured_attempts = int(os.environ.get("DEEPSEEK_MAX_TRANSPORT_ATTEMPTS", "2"))
        self._max_transport_attempts = max(1, max_transport_attempts or configured_attempts)
        self._thinking_enabled = os.environ.get("DEEPSEEK_THINKING", "enabled").lower() != "disabled"
        self._reasoning_effort = os.environ.get("DEEPSEEK_REASONING_EFFORT", "high")
        self._max_tokens = int(os.environ.get("DEEPSEEK_MAX_TOKENS", "65536"))
        self._client = client or httpx.Client()

    def complete_json(
        self,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
        schema: dict[str, Any],
        prompt_version: str,
        on_stream_event: StreamEventCallback | None = None,
    ) -> ProviderResponse:
        request_body: dict[str, Any] = {
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
            "stream": True,
            "stream_options": {"include_usage": True},
            "max_tokens": self._max_tokens,
            "thinking": {"type": "enabled" if self._thinking_enabled else "disabled"},
        }
        if self._thinking_enabled:
            request_body["reasoning_effort"] = self._reasoning_effort
        else:
            request_body["temperature"] = 0

        last_error: BaseException | None = None
        deadline = time.monotonic() + self._total_timeout_seconds
        for attempt in range(1, self._max_transport_attempts + 1):
            if time.monotonic() >= deadline:
                raise ModelTimeoutError("DeepSeek total generation deadline exceeded")
            if on_stream_event:
                on_stream_event({"phase": "request_started", "attempt": attempt})
            try:
                return self._complete_stream_attempt(
                    request_body=request_body,
                    prompt_version=prompt_version,
                    attempt=attempt,
                    deadline=deadline,
                    on_stream_event=on_stream_event,
                )
            except ModelOutputTruncatedError:
                raise
            except (httpx.TimeoutException, httpx.TransportError, ModelStreamInterruptedError) as exc:
                last_error = exc
                if attempt >= self._max_transport_attempts:
                    break
                if on_stream_event:
                    on_stream_event(
                        {
                            "phase": "retrying",
                            "attempt": attempt + 1,
                            "reason": type(exc).__name__,
                        }
                    )
                time.sleep(min(2.0 * attempt, 5.0))

        if isinstance(last_error, httpx.TimeoutException):
            raise ModelTimeoutError("DeepSeek stream timed out") from last_error
        raise ModelStreamInterruptedError("DeepSeek stream was interrupted") from last_error

    def _complete_stream_attempt(  # noqa: PLR0915
        self,
        *,
        request_body: dict[str, Any],
        prompt_version: str,
        attempt: int,
        deadline: float,
        on_stream_event: StreamEventCallback | None,
    ) -> ProviderResponse:
        started = time.monotonic()
        first_chunk_at: float | None = None
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        reasoning_chars = 0
        content_chars = 0
        usage: dict[str, Any] = {}
        finish_reason: str | None = None
        done = False

        try:
            with self._client.stream(
                "POST",
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "text/event-stream",
                },
                json=request_body,
                timeout=self._timeout,
            ) as response:
                response.raise_for_status()
                for raw_line in response.iter_lines():
                    now = time.monotonic()
                    if now >= deadline:
                        raise ModelTimeoutError("DeepSeek total generation deadline exceeded")
                    line = raw_line.strip()
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        done = True
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise ModelStreamInterruptedError("DeepSeek returned malformed SSE data") from exc
                    if first_chunk_at is None:
                        first_chunk_at = now
                    chunk_usage = chunk.get("usage")
                    if isinstance(chunk_usage, dict):
                        usage = dict(chunk_usage)
                    choices = chunk.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        continue
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
                    delta = choice.get("delta")
                    if not isinstance(delta, dict):
                        continue
                    reasoning_delta = delta.get("reasoning_content")
                    content_delta = delta.get("content")
                    if isinstance(reasoning_delta, str) and reasoning_delta:
                        reasoning_parts.append(reasoning_delta)
                        reasoning_chars += len(reasoning_delta)
                    if isinstance(content_delta, str) and content_delta:
                        content_parts.append(content_delta)
                        content_chars += len(content_delta)
                    if on_stream_event and (reasoning_delta or content_delta):
                        on_stream_event(
                            {
                                "phase": "reasoning" if reasoning_delta else "answering",
                                "attempt": attempt,
                                "reasoning_chars": reasoning_chars,
                                "content_chars": content_chars,
                            }
                        )
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429 or status >= 500:
                raise ModelStreamInterruptedError(f"DeepSeek HTTP {status}") from exc
            raise ModelProviderError(f"DeepSeek rejected the request with HTTP {status}") from exc
        except ModelProviderError:
            raise
        except httpx.RemoteProtocolError as exc:
            raise ModelStreamInterruptedError("DeepSeek closed the chunked response early") from exc

        if not done:
            raise ModelStreamInterruptedError("DeepSeek stream ended before [DONE]")
        if finish_reason == "length":
            raise ModelOutputTruncatedError("DeepSeek output reached the token limit")

        content = "".join(content_parts).strip()
        reasoning_content = "".join(reasoning_parts)
        if not content:
            raise ModelInvalidOutputError("DeepSeek returned an empty final answer")
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ModelInvalidOutputError("DeepSeek returned invalid structured output") from exc
        if not isinstance(payload, dict):
            raise ModelInvalidOutputError("DeepSeek structured output must be an object")

        finished = time.monotonic()
        timings = {
            "time_to_first_chunk_seconds": round((first_chunk_at or finished) - started, 3),
            "total_seconds": round(finished - started, 3),
        }
        if on_stream_event:
            on_stream_event(
                {
                    "phase": "completed",
                    "attempt": attempt,
                    "reasoning_chars": len(reasoning_content),
                    "content_chars": len(content),
                    "finish_reason": finish_reason,
                    "usage": usage,
                    "timings": timings,
                }
            )
        return ProviderResponse(
            payload=payload,
            model_id=self._model_id,
            prompt_version=prompt_version,
            reasoning_content=reasoning_content,
            usage=usage,
            finish_reason=finish_reason,
            streamed=True,
            transport_attempts=attempt,
            timings=timings,
        )
