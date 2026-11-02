import json
from types import SimpleNamespace
from typing import Any

import pytest

from tranpro.library.models import Segment
from tranpro.summarization.models import SummaryRequest
from tranpro.summarization.ollama import SummarizationError
from tranpro.summarization.openai import OpenAISummaryProvider


class FakeResponses:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


class FakeClient:
    def __init__(self, response: Any) -> None:
        self.responses = FakeResponses(response)


def test_openai_uses_responses_structured_output_and_records_cost() -> None:
    content = json.dumps(
        {
            "sections": [
                {
                    "heading": "Overview",
                    "body": "Budget constraints create tradeoffs.",
                    "segment_refs": ["s000001"],
                }
            ]
        }
    )
    client = FakeClient(
        SimpleNamespace(
            output_text=content,
            usage=SimpleNamespace(
                input_tokens=1_000,
                output_tokens=200,
                input_tokens_details=SimpleNamespace(cached_tokens=100),
            ),
        )
    )
    provider = OpenAISummaryProvider(client=client)

    result = provider.summarize(
        SummaryRequest(
            "Be faithful.",
            "Write notes.",
            (Segment(0, 0, 1_000, "Households face budget constraints."),),
        )
    )

    assert result.sections[0].segment_refs == ("s000001",)
    assert result.usage == {
        "input_tokens": 1_000,
        "output_tokens": 200,
        "cached_input_tokens": 100,
        "estimated_cost_usd": 0.001905,
    }
    request = client.responses.kwargs
    assert request is not None
    assert request["model"] == "gpt-6.1-terra"
    assert request["store"] is False
    assert request["reasoning"] == {"effort": "none"}
    assert request["text"]["format"]["strict"] is True


def test_openai_rejects_invalid_structured_content() -> None:
    client = FakeClient(
        SimpleNamespace(
            output_text='{"sections": []}',
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        )
    )

    with pytest.raises(SummarizationError, match="invalid structured"):
        OpenAISummaryProvider(client=client).summarize(
            SummaryRequest("Contract", "Instructions", (Segment(0, 0, 1, "Text"),))
        )


def test_openai_context_default_avoids_long_context_pricing_threshold() -> None:
    provider = OpenAISummaryProvider(client=FakeClient(None))

    assert provider.context_window.max_tokens == 272_000
    assert provider.context_window.input_limit < 272_000


def test_unknown_model_does_not_claim_a_cost_estimate() -> None:
    client = FakeClient(
        SimpleNamespace(
            output_text=json.dumps(
                {
                    "sections": [
                        {
                            "heading": "Notes",
                            "body": "Body",
                            "segment_refs": ["s000001"],
                        }
                    ]
                }
            ),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )
    )

    result = OpenAISummaryProvider(model="custom-model", client=client).summarize(
        SummaryRequest("Contract", "Notes", (Segment(0, 0, 1, "Text"),))
    )

    assert "estimated_cost_usd" not in result.usage
