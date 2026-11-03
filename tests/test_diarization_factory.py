import pytest

from tranpro.diarization.factory import build_diarization_provider
from tranpro.diarization.models import DiarizationError
from tranpro.diarization.nemotron_mlx import NemotronMLXProvider


def test_factory_builds_nemotron_from_profile_and_overrides() -> None:
    provider = build_diarization_provider(
        {
            "diarization_provider": "nemotron-mlx",
            "diarization_model": "configured/model",
            "diarization_preset": "low",
            "diarization_threshold": 0.4,
        },
        model_override="chosen/model",
        threshold_override=0.55,
    )

    assert isinstance(provider, NemotronMLXProvider)
    assert provider.model == "chosen/model"
    assert provider.preset == "low"
    assert provider.threshold == 0.55


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(DiarizationError, match="Unsupported"):
        build_diarization_provider({"diarization_provider": "mystery"})
