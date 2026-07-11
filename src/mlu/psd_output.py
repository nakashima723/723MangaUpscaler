"""Minimal layered grayscale PSD output.

The writer implements the documented PSD v1 sections needed by this project:
an 8- or 16-bit grayscale composite plus full-canvas pixel layers.  Each ink
layer stores black grayscale pixels and a transparency channel, matching the
existing PNG convention while keeping line art and tone independently editable.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mlu.grayscale import FloatImage

PSD_SIGNATURE = b"8BPS"
PSD_VERSION = 1
PSD_COLOR_MODE_GRAYSCALE = 1
PSD_COMPRESSION_RLE = 1
PSD_MAX_DIMENSION = 30_000


@dataclass(frozen=True)
class _PsdLayer:
    name: str
    channels: tuple[tuple[int, bytes], ...]
    blend_mode: bytes = b"norm"


def save_layered_grayscale_psd(
    path: str | Path,
    *,
    line_image: FloatImage,
    tone_image: FloatImage,
    bit_depth: int = 8,
    overwrite: bool = False,
) -> None:
    """Save line art and tone as editable layers in a grayscale PSD.

    The layer stack is, from top to bottom, ``Line Art``, ``Grayscale Tone``,
    and ``Background``.  The first two layers use black pixels with a
    transparency channel.  Their merged appearance is therefore equivalent to
    compositing the current separated PNG pair over white.
    """

    output_path = Path(path)
    if output_path.suffix.lower() != ".psd":
        raise ValueError("Layered grayscale output path must use the .psd extension.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {output_path}")
    if line_image.shape != tone_image.shape:
        raise ValueError("PSD line and tone layers must have the same dimensions.")
    if line_image.ndim != 2:
        raise ValueError("PSD line and tone layers must be 2D grayscale arrays.")
    if bit_depth not in {8, 16}:
        raise ValueError("PSD bit_depth must be 8 or 16.")

    height, width = line_image.shape
    if width < 1 or height < 1:
        raise ValueError("PSD dimensions must be positive.")
    if width > PSD_MAX_DIMENSION or height > PSD_MAX_DIMENSION:
        raise ValueError("PSD dimensions must not exceed 30000 pixels.")

    line_alpha = np.float32(1.0) - np.clip(line_image, 0.0, 1.0)
    tone_alpha = np.float32(1.0) - np.clip(tone_image, 0.0, 1.0)
    composite = np.clip(tone_image * line_image, 0.0, 1.0)
    black = np.zeros_like(line_image, dtype=np.float32)
    white = np.ones_like(line_image, dtype=np.float32)

    # PSD layer records are stored from bottom to top.  Applications render the
    # last record at the top of the layer palette, so keep Background first in
    # the file even though the user-facing stack is documented top to bottom.
    layers = (
        _PsdLayer(
            name="Background",
            channels=((0, _compress_channel(white, bit_depth)),),
        ),
        _PsdLayer(
            name="Grayscale Tone",
            channels=(
                (0, _compress_channel(black, bit_depth)),
                (-1, _compress_channel(tone_alpha, bit_depth)),
            ),
        ),
        _PsdLayer(
            name="Line Art",
            channels=(
                (0, _compress_channel(black, bit_depth)),
                (-1, _compress_channel(line_alpha, bit_depth)),
            ),
        ),
    )

    payload = _build_psd(
        width=width,
        height=height,
        bit_depth=bit_depth,
        layers=layers,
        composite_channel=_compress_channel(composite, bit_depth),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.tmp")
    try:
        temporary_path.write_bytes(payload)
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _build_psd(
    *,
    width: int,
    height: int,
    bit_depth: int,
    layers: tuple[_PsdLayer, ...],
    composite_channel: bytes,
) -> bytes:
    header = b"".join(
        (
            PSD_SIGNATURE,
            _u16(PSD_VERSION),
            b"\x00" * 6,
            _u16(1),
            _u32(height),
            _u32(width),
            _u16(bit_depth),
            _u16(PSD_COLOR_MODE_GRAYSCALE),
        )
    )
    color_mode_data = _u32(0)
    image_resources = _u32(0)
    layer_and_mask = _layer_and_mask_section(width, height, layers)
    image_data = _u16(PSD_COMPRESSION_RLE) + composite_channel
    return header + color_mode_data + image_resources + layer_and_mask + image_data


def _layer_and_mask_section(
    width: int,
    height: int,
    layers: tuple[_PsdLayer, ...],
) -> bytes:
    records = bytearray()
    channel_data = bytearray()
    for layer in layers:
        records.extend(_layer_record(width, height, layer))
        for _channel_id, compressed in layer.channels:
            channel_data.extend(_u16(PSD_COMPRESSION_RLE))
            channel_data.extend(compressed)

    layer_info_data = _i16(len(layers)) + bytes(records) + bytes(channel_data)
    if len(layer_info_data) % 2:
        layer_info_data += b"\x00"
    layer_info = _u32(len(layer_info_data)) + layer_info_data
    global_layer_mask = _u32(0)
    section = layer_info + global_layer_mask
    return _u32(len(section)) + section


def _layer_record(width: int, height: int, layer: _PsdLayer) -> bytes:
    channel_info = b"".join(
        _i16(channel_id) + _u32(2 + len(compressed))
        for channel_id, compressed in layer.channels
    )
    name = _pascal_string(layer.name)
    extra = _u32(0) + _u32(0) + name
    return b"".join(
        (
            _i32(0),
            _i32(0),
            _i32(height),
            _i32(width),
            _u16(len(layer.channels)),
            channel_info,
            b"8BIM",
            layer.blend_mode,
            b"\xff\x00\x00\x00",
            _u32(len(extra)),
            extra,
        )
    )


def _compress_channel(array: FloatImage, bit_depth: int) -> bytes:
    clipped = np.clip(array, 0.0, 1.0)
    if bit_depth == 8:
        rows = np.rint(clipped * np.float32(255.0)).astype(np.uint8)
    else:
        rows = (
            np.rint(clipped * np.float32(65535.0))
            .astype(np.uint16)
            .astype(">u2", copy=False)
        )
    encoded_rows = tuple(_packbits(row.tobytes()) for row in rows)
    if any(len(row) > 65535 for row in encoded_rows):
        raise ValueError("PSD RLE row exceeds the PSD v1 length limit.")
    byte_counts = b"".join(_u16(len(row)) for row in encoded_rows)
    return byte_counts + b"".join(encoded_rows)


def _packbits(data: bytes) -> bytes:
    """Encode one scanline with the PackBits variant used by PSD RLE."""

    output = bytearray()
    index = 0
    size = len(data)
    while index < size:
        run_length = 1
        while (
            index + run_length < size
            and run_length < 128
            and data[index + run_length] == data[index]
        ):
            run_length += 1
        if run_length >= 3:
            output.append(257 - run_length)
            output.append(data[index])
            index += run_length
            continue

        literal_start = index
        index += run_length
        while index < size and index - literal_start < 128:
            next_run = 1
            while (
                index + next_run < size
                and next_run < 128
                and data[index + next_run] == data[index]
            ):
                next_run += 1
            if next_run >= 3:
                break
            if index - literal_start + next_run > 128:
                index = literal_start + 128
                break
            index += next_run
        literal = data[literal_start:index]
        output.append(len(literal) - 1)
        output.extend(literal)
    return bytes(output)


def _pascal_string(value: str) -> bytes:
    encoded = value.encode("ascii")
    if len(encoded) > 255:
        raise ValueError("PSD layer names must fit in a Pascal string.")
    data = bytes((len(encoded),)) + encoded
    return data + b"\x00" * ((-len(data)) % 4)


def _u16(value: int) -> bytes:
    return struct.pack(">H", value)


def _i16(value: int) -> bytes:
    return struct.pack(">h", value)


def _u32(value: int) -> bytes:
    return struct.pack(">I", value)


def _i32(value: int) -> bytes:
    return struct.pack(">i", value)
