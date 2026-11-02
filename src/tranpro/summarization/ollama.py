"""Ollama adapter using its local HTTP API and structured outputs."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tranpro.library.models import SummarySection
from tranpro.summarization.models import (
    ContextWindow,
    SummaryRequest,
    SummaryResult,
)
from tranpro.summarization.planner import render_segments

DEFAULT_OLLAMA_MODEL = "gemma4:12b"
DEFAULT_CONTEXT_TOKENS = 65_536

_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "body": {"type": "string"},
                    "segment_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                },
                "required": ["heading", "body", "segment_refs"],
                "additionalProperties": False,
            },
            "minItems": 1,
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}


class SummarizationError(RuntimeError):
    """Raised when a summary provider or workflow cannot produce a result."""


@dataclass(slots=True)
class OllamaProvider:
    """Generate grounded JSON summaries through a local Ollama server."""

    model: str = DEFAULT_OLLAMA_MODEL
    base_url: str = "http://127.0.0.1:11434"
    context_tokens: int = DEFAULT_CONTEXT_TOKENS
    output_tokens: int = 4_096
    timeout_seconds: float = 900.0

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def context_window(self) -> ContextWindow:
        return ContextWindow(
            max_tokens=self.context_tokens,
            reserved_output_tokens=self.output_tokens,
            safety_margin_tokens=1_024,
        )

    def count_tokens(self, text: str) -> int:
        """Conservatively estimate tokens before Ollama reports actual usage."""

        if not text:
            return 0
        return max(1, math.ceil(len(text.encode("utf-8")) / 3))

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        user_content = _render_request(request)
        payload = {
            "model": self.model,
            "stream": False,
            "format": _SUMMARY_SCHEMA,
            "messages": [
                {"role": "system", "content": request.system_contract},
                {"role": "user", "content": user_content},
            ],
            "options": {
                "temperature": 0,
                "num_ctx": self.context_tokens,
                "num_predict": self.output_tokens,
            },
        }
        response = self._post("/api/chat", payload)
        try:
            message = cast(dict[str, Any], response["message"])
            raw_text = str(message["content"])
            parsed = cast(dict[str, Any], json.loads(raw_text))
            raw_sections = cast(list[dict[str, Any]], parsed["sections"])
            sections = tuple(
                SummarySection(
                    heading=str(section["heading"]).strip(),
                    body=str(section["body"]).strip(),
                    segment_refs=tuple(
                        str(ref) for ref in cast(list[Any], section["segment_refs"])
                    ),
                )
                for section in raw_sections
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise SummarizationError(
                "Ollama returned an invalid structured summary"
            ) from error
        if not sections or any(not item.heading or not item.body for item in sections):
            raise SummarizationError("Ollama returned an empty summary section")
        if any(not item.segment_refs for item in sections):
            raise SummarizationError("Ollama returned an ungrounded summary section")
        usage: dict[str, int | float] = {}
        for source, destination in (
            ("prompt_eval_count", "input_tokens"),
            ("eval_count", "output_tokens"),
            ("total_duration", "duration_ns"),
        ):
            value = response.get(source)
            if isinstance(value, int | float):
                usage[destination] = value
        return SummaryResult(sections=sections, raw_text=raw_text, usage=usage)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url.rstrip('/')}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code == 404 and "model" in detail.lower():
                raise SummarizationError(
                    f"Ollama model {self.model!r} is not installed; "
                    f"run `ollama pull {self.model}`"
                ) from error
            raise SummarizationError(
                f"Ollama request failed ({error.code}): {detail}"
            ) from error
        except (URLError, TimeoutError, OSError) as error:
            raise SummarizationError(
                "Could not reach Ollama at "
                f"{self.base_url}; install and start Ollama, then retry"
            ) from error
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as error:
            raise SummarizationError("Ollama returned invalid JSON") from error
        if not isinstance(decoded, dict):
            raise SummarizationError("Ollama returned an unexpected response")
        return cast(dict[str, Any], decoded)


def _render_request(request: SummaryRequest) -> str:
    if request.source_notes:
        source = "\n\n".join(
            f"Partial notes {index + 1}:\n{notes}"
            for index, notes in enumerate(request.source_notes)
        )
        source_label = "Partial notes to synthesize"
    else:
        source = render_segments(request.segments)
        source_label = "Transcript"
    return (
        f"{request.instructions}\n\n"
        "Return valid JSON matching the supplied schema. Preserve only segment "
        "references that appear in the input.\n\n"
        f"{source_label}:\n{source}"
    )
