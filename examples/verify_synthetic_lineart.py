"""Verify that regenerating the public sample preserves every decoded pixel."""

from pathlib import Path

from generate_synthetic_lineart import main as generate_sample
from PIL import Image


def _load_pixels(path: Path) -> tuple[str, tuple[int, int], bytes]:
    with Image.open(path) as image:
        image.load()
        return image.mode, image.size, image.tobytes()


def main() -> None:
    sample_path = Path(__file__).with_name("synthetic_lineart.png")
    expected = _load_pixels(sample_path)
    generate_sample()
    actual = _load_pixels(sample_path)
    if actual != expected:
        raise SystemExit("Regenerated synthetic sample pixels differ from the committed image.")
    print("Synthetic sample pixels are reproducible.")


if __name__ == "__main__":
    main()
