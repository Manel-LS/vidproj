"""Download the depth model used for 2.5D parallax.

Deliberately a separate, explicit command rather than a download on first use.
Fetching 27 MB the first time somebody clicks Render — silently, from a host they
did not choose — is not something the app should do behind their back.

    python scripts/fetch_depth_model.py            # quantised, 27 MB (default)
    python scripts/fetch_depth_model.py --full     # float32, 99 MB, marginally better

The file lands where `DEPTH_MODEL_PATH` points, and nothing reads it until
`DEPTH_PROVIDER=onnx` is set.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402

BASE = "https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx"
VARIANTS = {
    # Quantised is the default on purpose: a third of the size, and the depth map
    # feeds a displacement that is then resampled — the precision lost does not
    # survive to the screen anyway.
    "quantised": f"{BASE}/model_quantized.onnx",
    "full": f"{BASE}/model.onnx",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="download the float32 model (99 MB)")
    parser.add_argument("--output", default=settings.depth_model_path)
    args = parser.parse_args()

    url = VARIANTS["full" if args.full else "quantised"]
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.is_file():
        print(f"Already present: {target} ({target.stat().st_size / 1e6:.1f} MB)")
        return 0

    print(f"Downloading {url}\n         -> {target}")
    # Written to a temporary name and moved into place, so an interrupted download
    # cannot leave a truncated file that ONNX Runtime would fail to load with a
    # message pointing at the wrong problem.
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            written = 0
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(1 << 20):
                    handle.write(chunk)
                    written += len(chunk)
                    if total:
                        print(f"  {written / 1e6:6.1f} / {total / 1e6:.1f} MB", end="\r")
    except httpx.HTTPError as exc:
        partial.unlink(missing_ok=True)
        print(f"\nDownload failed: {exc}")
        return 1

    partial.replace(target)
    print(f"\nSaved {target} ({target.stat().st_size / 1e6:.1f} MB)")
    print("\nNow set DEPTH_PROVIDER=onnx in backend/.env and restart the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
