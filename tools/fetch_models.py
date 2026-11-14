"""Download the pretrained detector models into models/pretrained/ (standard library only)."""
import sys
import urllib.request
from pathlib import Path

DEST = Path(__file__).resolve().parent.parent / "models" / "pretrained"

FILES = {
    "yolox_nano.onnx": (
        "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx",
        3659407,
    ),
    "inat_bird.tflite": (
        "https://raw.githubusercontent.com/google-coral/test_data/master/mobilenet_v2_1.0_224_inat_bird_quant.tflite",
        3579500,
    ),
    "inat_bird_labels.txt": (
        "https://raw.githubusercontent.com/google-coral/test_data/master/inat_bird_labels.txt",
        37146,
    ),
}


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    failed = False
    for name, (url, size) in FILES.items():
        target = DEST / name
        if target.is_file() and target.stat().st_size == size:
            print(f"ok      {name}")
            continue
        print(f"fetch   {name}")
        partial = target.with_name(name + ".part")
        with urllib.request.urlopen(url, timeout=60) as response, open(partial, "wb") as out:
            while chunk := response.read(1 << 16):
                out.write(chunk)
        got = partial.stat().st_size
        if got != size:
            partial.unlink()
            print(f"error   {name}: expected {size} bytes, got {got}", file=sys.stderr)
            failed = True
            continue
        partial.replace(target)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
