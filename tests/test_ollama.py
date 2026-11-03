import json
from typing import Any

import pytest

from tranpro.library.models import Segment
from tranpro.summarization.models import SummaryRequest
from tranpro.summarization.ollama import OllamaProvider, SummarizationError


class StubOllama(OllamaProvider):
    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__(model="gemma4:12b")
        self.response = response
        self.payload: dict[str, Any] | None = None

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert path == "/api/chat"
        self.payload = payload
        return self.response


def test_ollama_requests_deterministic_structured_output() -> None:
    response_content = {
        "sections": [
            {
                "heading": "Overview",
                "body": "The speaker explains scarcity.",
                "segment_refs": ["s000001"],
            }
        ]
    }
    provider = StubOllama(
        {
            "message": {"content": json.dumps(response_content)},
            "prompt_eval_count": 40,
            "eval_count": 20,
        }
    )

    result = provider.summarize(
        SummaryRequest(
            system_contract="Be faithful.",
            instructions="Write notes.",
            segments=(Segment(0, 0, 1_000, "Scarcity matters."),),
        )
    )

    assert result.sections[0].segment_refs == ("s000001",)
    assert result.usage == {"input_tokens": 40, "output_tokens": 20}
    assert provider.payload is not None
    assert provider.payload["format"]["properties"]["sections"]["minItems"] == 1
    assert provider.payload["options"]["temperature"] == 0
    assert provider.payload["options"]["num_ctx"] == 65_536


def test_ollama_rejects_ungrounded_sections() -> None:
    provider = StubOllama(
        {
            "message": {
                "content": json.dumps(
                    {
                        "sections": [
                            {
                                "heading": "Overview",
                                "body": "Body",
                                "segment_refs": [],
                            }
                        ]
                    }
                )
            }
        }
    )

    with pytest.raises(SummarizationError, match="ungrounded"):
        provider.summarize(
            SummaryRequest("Contract", "Instructions", (Segment(0, 0, 1, "x"),))
        )
