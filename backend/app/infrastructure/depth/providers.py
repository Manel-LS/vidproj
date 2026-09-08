"""Concrete depth estimators.

Only one for now — Depth Anything V2 Small, run through ONNX Runtime on the CPU.
It was chosen for what it costs rather than for what it scores: the quantised
export is 27 MB and takes one to two seconds for a 1080x1920 image on a laptop
CPU, which is the difference between an effect every project can afford and one
reserved for a GPU box.

Both the runtime and the model file are optional. `is_available()` answers for the
pair, so a deployment that has neither behaves exactly like one that has no
provider configured.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.infrastructure.depth.base import DepthMap, DepthProvider, DepthUnavailable

logger = get_logger(__name__)

#: ImageNet statistics the model was trained with.
_MEAN = (0.485, 0.456, 0.406)
_STD = (0.229, 0.224, 0.225)
#: The backbone works on patches of 14, so the input side must be a multiple of it.
_PATCH = 14


class OnnxDepthProvider(DepthProvider):
    name = "onnx"
    display_name = "Depth Anything V2 Small (local, CPU)"

    def __init__(self, model_path: str = ""):
        self._model_path = Path(model_path or settings.depth_model_path)
        self._session = None

    # -- availability --------------------------------------------------------

    @staticmethod
    def _runtime_installed() -> bool:
        try:
            import numpy  # noqa: F401, PLC0415
            import onnxruntime  # noqa: F401, PLC0415
        except ImportError:
            return False
        return True

    def is_available(self) -> bool:
        return self._runtime_installed() and self._model_path.is_file()

    @property
    def model_path(self) -> Path:
        return self._model_path

    def unavailable_reason(self) -> str:
        if not self._runtime_installed():
            return (
                "Depth-based parallax needs the optional ONNX runtime. Install it with "
                "`pip install -r requirements-depth.txt`."
            )
        if not self._model_path.is_file():
            return (
                f"The depth model was not found at {self._model_path}. Download it with "
                "`python scripts/fetch_depth_model.py`."
            )
        return ""

    # -- inference -----------------------------------------------------------

    def _get_session(self):
        if self._session is None:
            import onnxruntime as ort  # noqa: PLC0415

            options = ort.SessionOptions()
            # One thread per core would fight the render for the CPU; the model is
            # small enough that the extra threads buy very little anyway.
            options.intra_op_num_threads = max(1, settings.depth_threads)
            self._session = ort.InferenceSession(
                str(self._model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        return self._session

    def estimate(self, image_path, *, max_size: int = 0) -> DepthMap:
        if not self.is_available():
            raise DepthUnavailable(self.unavailable_reason())

        import numpy as np  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415

        side = max_size or settings.depth_input_size
        side = max(_PATCH, (side // _PATCH) * _PATCH)

        try:
            with Image.open(image_path) as handle:
                source = handle.convert("RGB")
                # Squashed to a square rather than letterboxed: the model is scale
                # tolerant, and padding would put a band of invented pixels at the
                # edge, which reads as a wall standing beside the subject.
                small = source.resize((side, side), Image.BILINEAR)

            array = np.asarray(small, dtype=np.float32) / 255.0
            array = (array - np.array(_MEAN, dtype=np.float32)) / np.array(_STD, dtype=np.float32)
            tensor = array.transpose(2, 0, 1)[None]

            session = self._get_session()
            raw = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]
        except DepthUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Depth estimation failed for %s: %s", image_path, exc)
            raise DepthUnavailable(
                "The depth model could not read this image, so the scene keeps its flat animation."
            ) from exc

        span = float(raw.max() - raw.min())
        if span <= 1e-6:
            # A perfectly flat prediction is a real answer — a blank or a solid
            # colour — and normalising it would amplify noise into fake structure.
            normalised = np.zeros_like(raw)
        else:
            normalised = (raw - raw.min()) / span

        height, width = normalised.shape
        return DepthMap(
            width=int(width),
            height=int(height),
            values=tuple(float(value) for value in normalised.reshape(-1)),
        )
