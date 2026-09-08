"""Depth estimation: the abstraction, and the honesty around it.

No network and no model file are required to run these. The ONNX path is exercised
only when the optional runtime and the model are both present, because a test that
silently skips the real work is better than a suite that cannot run on a fresh
checkout — and the behaviour that actually matters when they are absent is that
the app degrades instead of failing.
"""
from __future__ import annotations

import pytest

from app.infrastructure.depth.base import (
    DepthMap,
    DepthProvider,
    DepthUnavailable,
    NullDepthProvider,
)
from app.infrastructure.depth.factory import depth_status, get_depth_provider
from app.infrastructure.depth.providers import OnnxDepthProvider

API = "/api/v1"


def _has_model() -> bool:
    return OnnxDepthProvider().is_available()


requires_model = pytest.mark.skipif(
    not _has_model(),
    reason="optional depth runtime or model file not installed",
)


# --------------------------------------------------------------- the shape --


def test_a_depth_map_reads_row_major():
    depth = DepthMap(width=2, height=2, values=(0.0, 0.25, 0.5, 1.0))
    assert depth.at(0, 0) == 0.0
    assert depth.at(1, 0) == 0.25
    assert depth.at(0, 1) == 0.5
    assert depth.at(1, 1) == 1.0


def test_the_map_carries_no_flatness_helper():
    """Guards a helper that was written, measured, and removed.

    Normalising to [0, 1] makes the spread of the values near-constant, so a
    screenshot of a web page and a landscape both span the full range. A helper
    that claimed to tell them apart would be believed.
    """
    assert not hasattr(DepthMap(width=1, height=1, values=(0.5,)), "spread")


# ------------------------------------------------------------- degradation --


def test_without_a_provider_nothing_is_invented():
    provider = NullDepthProvider()
    assert provider.is_available() is False
    with pytest.raises(DepthUnavailable):
        provider.estimate("anything.jpg")


def test_the_default_deployment_reports_depth_as_unavailable(client):
    # DEPTH_PROVIDER is unset in the test environment, as in a fresh install.
    body = client.get(f"{API}/capabilities").json()
    assert "depth" in body
    assert body["depth"]["available"] is False
    assert body["depth"]["message"], "an unavailable feature has to say why"


def test_the_status_explains_which_piece_is_missing():
    status = depth_status()
    assert status["available"] is False
    # Not a generic failure: the message names the thing to fix.
    assert any(word in status["message"].lower() for word in ("configured", "install", "download"))


def test_an_unconfigured_provider_is_still_the_null_one():
    assert isinstance(get_depth_provider(), (NullDepthProvider, OnnxDepthProvider))
    assert get_depth_provider().is_available() is False


def test_a_missing_model_is_reported_as_a_missing_model(tmp_path):
    provider = OnnxDepthProvider(model_path=str(tmp_path / "absent.onnx"))
    assert provider.is_available() is False
    reason = provider.unavailable_reason()
    assert reason
    with pytest.raises(DepthUnavailable) as excinfo:
        provider.estimate(tmp_path / "whatever.jpg")
    assert str(excinfo.value) == reason


def test_providers_declare_the_contract():
    assert issubclass(OnnxDepthProvider, DepthProvider)
    assert issubclass(NullDepthProvider, DepthProvider)


# ------------------------------------------------------- the real estimator --


@requires_model
def test_depth_is_estimated_and_normalised(tmp_path, sample_images):
    source = tmp_path / "scene.jpg"
    source.write_bytes(sample_images(1)[0][1][1])

    depth = OnnxDepthProvider().estimate(source, max_size=224)
    assert depth.width > 0 and depth.height > 0
    assert len(depth.values) == depth.width * depth.height
    assert min(depth.values) >= 0.0 and max(depth.values) <= 1.0


@requires_model
def test_the_input_side_is_rounded_to_the_model_patch(tmp_path, sample_images):
    # The backbone works on patches of 14; an odd size would be silently reshaped
    # by the runtime, and the map would no longer line up with the image.
    source = tmp_path / "scene.jpg"
    source.write_bytes(sample_images(1)[0][1][1])

    depth = OnnxDepthProvider().estimate(source, max_size=100)
    assert depth.width % 14 == 0 and depth.height % 14 == 0


@requires_model
def test_an_unreadable_image_degrades_instead_of_crashing(tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"this is not an image")
    with pytest.raises(DepthUnavailable):
        OnnxDepthProvider().estimate(broken)
