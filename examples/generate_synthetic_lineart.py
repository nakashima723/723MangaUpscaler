"""Generate the redistribution-safe line-art sample used by public examples."""

from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    output = Path(__file__).with_name("synthetic_lineart.png")
    image = Image.new("L", (320, 240), 255)
    draw = ImageDraw.Draw(image)
    draw.line([(22, 205), (92, 112), (159, 164), (236, 66), (298, 121)], fill=0, width=3)
    draw.rectangle((48, 42, 132, 112), outline=0, width=2)
    draw.line([(48, 42), (90, 15), (132, 42)], fill=0, width=2)
    draw.ellipse((205, 132, 277, 204), outline=0, width=2)
    draw.arc((217, 143, 265, 191), 205, 335, fill=96, width=2)
    draw.line([(18, 220), (302, 220)], fill=64, width=1)
    image.save(output, optimize=True)
    print(output)


if __name__ == "__main__":
    main()
