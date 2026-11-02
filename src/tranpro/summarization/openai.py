"""Hosted OpenAI summary adapter using the Responses API."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI, OpenAIError

from tranpro.summarization.models import (
    ContextWindow,
    SummaryRequest,
    SummaryResult,
)
from tranpro.summarization.ollama import SummarizationError
from tranpro.summarization.structured import (
    SUMMARY_SCHEMA,
    parse_summary_text,
    render_summary_request,
)

DEFAULT_OPENAI_MODEL = "gpt-6.1-terra"
DEFAULT_OPENAI_CONTEXT_TOKENS = 272_000
_TERRA_INPUT_USD_PER_MILLION = 1.00
_TERRA_CACHED_INPUT_USD_PER_MILLION = 0.05
_TERRA_OUTPUT_USD_PER_MILLION = 5.00


@dataclass(slots=True)
class OpenAISummaryProvider:
    """Generate structured notes with an explicitly selected hosted model."""

    model: str = DEFAULT_OPENAI_MODEL
    context_tokens: int = DEFAULT_OPENAI_CONTEXT_TOKENS
    output_tokens: int = 8_192
    reasoning_effort: str = "none"
    client: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.client is None:
            try:
                self.client = OpenAI()
            except OpenAIError as error:
                raise SummarizationError(
                    "OpenAI is not configured; set OPENAI_API_KEY and retry"
                ) from error

    @property
    def name(self) -> str:
        return "openai"

    @property
    def context_window(self) -> ContextWindow:
        return ContextWindow(
            max_tokens=self.context_tokens,
            reserved_output_tokens=self.output_tokens,
            safety_margin_tokens=2_048,
        )

    def count_tokens(self, text: str) -> int:
        """Use a conservative preflight estimate; persist actual API usage."""

        if not text:
            return 0
        return max(1, math.ceil(len(text.encode("utf-8")) / 3))

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        try:
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": request.system_contract},
                    {
                        "role": "user",
                        "content": render_summary_request(request),
                    },
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "grounded_summary",
                        "strict": True,
                        "schema": SUMMARY_SCHEMA,
                    }
                },
                reasoning={"effort": self.reasoning_effort},
                max_output_tokens=self.output_tokens,
                store=False,
            )
            raw_text = str(response.output_text)
            sections = parse_summary_text(raw_text)
        except OpenAIError as error:
            raise SummarizationError(
                f"OpenAI summary request failed: {error}"
            ) from error
        except (KeyError, TypeError, ValueError) as error:
            raise SummarizationError(
                f"OpenAI returned an invalid structured summary: {error}"
            ) from error
        usage: dict[str, int | float] = {}
        input_tokens = getattr(response.usage, "input_tokens", None)
        output_tokens = getattr(response.usage, "output_tokens", None)
        input_details = getattr(response.usage, "input_tokens_details", None)
        cached_tokens = getattr(input_details, "cached_tokens", 0)
        if isinstance(input_tokens, int):
            usage["input_tokens"] = input_tokens
        if isinstance(output_tokens, int):
            usage["output_tokens"] = output_tokens
        if isinstance(cached_tokens, int) and cached_tokens > 0:
            usage["cached_input_tokens"] = cached_tokens
        if (
            self.model == DEFAULT_OPENAI_MODEL
            and isinstance(input_tokens, int)
            and isinstance(output_tokens, int)
            and isinstance(cached_tokens, int)
        ):
            uncached_tokens = max(0, input_tokens - cached_tokens)
            usage["estimated_cost_usd"] = (
                uncached_tokens * _TERRA_INPUT_USD_PER_MILLION
                + cached_tokens * _TERRA_CACHED_INPUT_USD_PER_MILLION
                + output_tokens * _TERRA_OUTPUT_USD_PER_MILLION
            ) / 1_000_000
        return SummaryResult(sections=sections, raw_text=raw_text, usage=usage)
