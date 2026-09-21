"""Live mic test for hey_xiaoai.onnx (or any openWakeWord model).

Prints rolling scores; announces HIT when score >= threshold.
Ctrl+C to stop.

  python test_wake.py
  python test_wake.py --threshold 0.6
  python test_wake.py --list-devices
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

WAKE_FRAME = 1280  # 80 ms @ 16 kHz
SAMPLE_RATE = 16000

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = HERE.parent / "models" / "hey_xiaoai.onnx"
FEATURE_MODELS = HERE / "train_workspace" / "custom-wakeword-trainer" / "data" / "models"
OWW_RELEASE = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1"


def _list_devices() -> None:
    import sounddevice as sd

    print(sd.query_devices())
    print("default input:", sd.default.device)


def _feature_paths() -> tuple[Path, Path]:
    """Resolve melspectrogram + embedding onnx (prefer trainer cache, else download beside it)."""
    FEATURE_MODELS.mkdir(parents=True, exist_ok=True)
    mel = FEATURE_MODELS / "melspectrogram.onnx"
    emb = FEATURE_MODELS / "embedding_model.onnx"
    for path in (mel, emb):
        if path.is_file():
            continue
        url = f"{OWW_RELEASE}/{path.name}"
        print(f"downloading {url} ...")
        from urllib.request import urlretrieve

        urlretrieve(url, path)
    return mel, emb


def _load_model(Model, spec: str):
    mel, emb = _feature_paths()
    models = [spec]
    last = None
    for framework in ("onnx", "tflite"):
        try:
            m = Model(
                wakeword_models=models,
                inference_framework=framework,
                melspec_model_path=str(mel),
                embedding_model_path=str(emb),
            )
            print(f"framework={framework}")
            return m
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise RuntimeError(f"cannot load model {spec}: {last}")


def main() -> int:
    p = argparse.ArgumentParser(description="Live wake-word mic test")
    p.add_argument("--model", default=str(DEFAULT_MODEL), help="path to .onnx")
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--device", default=None, help="sounddevice index or name")
    p.add_argument("--cooldown", type=float, default=1.2, help="min seconds between HITs (also needs re-arm)")
    p.add_argument(
        "--rearm-below",
        type=float,
        default=0.25,
        help="score must fall below this before another HIT counts (debounce)",
    )
    p.add_argument("--list-devices", action="store_true")
    args = p.parse_args()

    if args.list_devices:
        _list_devices()
        return 0

    model_path = Path(args.model)
    if not model_path.is_file():
        print(f"model not found: {model_path}", file=sys.stderr)
        return 1

    try:
        from openwakeword.model import Model
    except ImportError:
        print("pip install openwakeword", file=sys.stderr)
        return 1

    import numpy as np
    import sounddevice as sd

    device = args.device
    if device is not None and str(device).isdigit():
        device = int(device)

    oww = _load_model(Model, str(model_path.resolve()))
    print(f"model={model_path.resolve()}")
    print(
        f"threshold={args.threshold}  rearm_below={args.rearm_below}  "
        f"cooldown={args.cooldown}s  device={device!r}"
    )
    print("say: hey xiao ai / hey 小哀   (Ctrl+C to quit)")
    print("note: one utterance used to count many HITs; now needs score to drop first\n")

    buf = bytearray()
    hits = 0
    last_hit = 0.0
    last_print = 0.0
    armed = True  # must disarm after HIT until score falls

    def callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
        nonlocal hits, last_hit, last_print, armed
        if status:
            print(f"status={status}", flush=True)
        buf.extend(indata[:frames].tobytes())
        frame_bytes = WAKE_FRAME * 2
        while len(buf) >= frame_bytes:
            chunk = bytes(buf[:frame_bytes])
            del buf[:frame_bytes]
            pcm = np.frombuffer(chunk, dtype=np.int16)
            scores = oww.predict(pcm) or {}
            if not scores:
                continue
            name, score = max(scores.items(), key=lambda kv: float(kv[1]))
            score = float(score)
            now = time.monotonic()
            if score < args.rearm_below:
                armed = True
            if now - last_print >= 0.12:
                bar = "#" * int(min(score, 1.0) * 20)
                flag = " " if armed else "x"
                print(f"\r{flag} {score:5.3f} |{bar:<20}| {name}    ", end="", flush=True)
                last_print = now
            if (
                armed
                and score >= args.threshold
                and (now - last_hit) >= args.cooldown
            ):
                hits += 1
                last_hit = now
                armed = False
                print(f"\n>>> HIT #{hits}  score={score:.3f}  model={name}", flush=True)

    kwargs = dict(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=WAKE_FRAME,
        callback=callback,
    )
    if device is not None:
        kwargs["device"] = device

    try:
        with sd.InputStream(**kwargs):
            while True:
                time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"\nstopped. hits={hits}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
