"""Port implemented by local and hosted summary model adapters."""

from __future__ import annotations

from typing import Protocol

from tranpro.summarization.models import ContextWindow, SummaryRequest, SummaryResult


class SummaryProvider(Protocol):
    """A summary model without SDK-specific types leaking into workflows."""

    name: str
    model: str
    context_window: ContextWindow

    def count_tokens(self, text: str) -> int:
        """Return the provider-specific token count for text."""

    def summarize(self, request: SummaryRequest) -> SummaryResult:
        """Summarize one input that has already been checked for feasibility."""
