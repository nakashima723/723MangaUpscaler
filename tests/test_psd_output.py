from __future__ import annotations

import struct

import numpy as np
import pytest
from PIL import Image

from mlu.psd_output import _packbits, save_layered_grayscale_psd


def _layers() -> tuple[np.ndarray, np.ndarray]:
    tone = np.broadcast_to(
        np.linspace(0.30, 1.0, 18, dtype=np.float32),
        (12, 18),
    ).copy()
    line = np.ones_like(tone)
    line[3:10, 8:10] = np.float32(0.0)
    line[6:8, 2:16] = np.float32(0.35)
    return line, tone


def _decode_packbits(data: bytes) -> bytes:
    output = bytearray()
    index = 0
    while index < len(data):
        control = data[index]
        index += 1
        if control <= 127:
            length = control + 1
            output.extend(data[index : index + length])
            index += length
        elif control >= 129:
            length = 257 - control
            output.extend(data[index : index + 1] * length)
            index += 1
    return bytes(output)


def test_packbits_roundtrips_long_mixed_scanline() -> None:
    random = np.random.default_rng(723)
    data = bytearray(random.integers(0, 256, 2896, dtype=np.uint8).tobytes())
    data[120:340] = b"\x00" * 220
    data[1500:1700] = b"\xff" * 200

    encoded = _packbits(bytes(data))

    assert _decode_packbits(encoded) == bytes(data)


def test_save_layered_grayscale_psd_has_layers_and_exact_8bit_composite(
    tmp_path,
) -> None:
    line, tone = _layers()
    output = tmp_path / "layers.psd"

    save_layered_grayscale_psd(
        output,
        line_image=line,
        tone_image=tone,
        bit_depth=8,
    )

    payload = output.read_bytes()
    assert payload[:4] == b"8BPS"
    assert struct.unpack(">H", payload[4:6])[0] == 1
    assert struct.unpack(">H", payload[12:14])[0] == 1
    assert struct.unpack(">I", payload[14:18])[0] == 12
    assert struct.unpack(">I", payload[18:22])[0] == 18
    assert struct.unpack(">H", payload[22:24])[0] == 8
    assert struct.unpack(">H", payload[24:26])[0] == 1
    assert b"Line Art" in payload
    assert b"Grayscale Tone" in payload
    assert b"Background" in payload
    assert (
        payload.index(b"Background")
        < payload.index(b"Grayscale Tone")
        < payload.index(b"Line Art")
    )

    with Image.open(output) as image:
        assert image.format == "PSD"
        assert image.mode == "L"
        assert image.size == (18, 12)
        composite = np.asarray(image.copy())
    expected = np.rint(np.clip(tone * line, 0.0, 1.0) * 255.0).astype(np.uint8)
    np.testing.assert_array_equal(composite, expected)


def test_save_layered_grayscale_psd_supports_16bit_document_depth(tmp_path) -> None:
    line, tone = _layers()
    output = tmp_path / "layers16.psd"

    save_layered_grayscale_psd(
        output,
        line_image=line,
        tone_image=tone,
        bit_depth=16,
    )

    payload = output.read_bytes()
    assert struct.unpack(">H", payload[22:24])[0] == 16
    assert b"Line Art" in payload
    assert b"Grayscale Tone" in payload


def test_save_layered_grayscale_psd_checks_extension_shape_and_overwrite(
    tmp_path,
) -> None:
    line, tone = _layers()
    output = tmp_path / "layers.psd"
    save_layered_grayscale_psd(output, line_image=line, tone_image=tone)

    with pytest.raises(FileExistsError):
        save_layered_grayscale_psd(output, line_image=line, tone_image=tone)
    with pytest.raises(ValueError, match=".psd"):
        save_layered_grayscale_psd(
            tmp_path / "layers.png",
            line_image=line,
            tone_image=tone,
        )
    with pytest.raises(ValueError, match="same dimensions"):
        save_layered_grayscale_psd(
            tmp_path / "mismatch.psd",
            line_image=line,
            tone_image=tone[:-1],
        )
