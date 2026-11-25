# SPDX-License-Identifier: AGPL-3.0-or-later
"""A place's map art made into its scene (the operator, 2026-11-25: "MAPS ARE STILL FUCKING
BROKEN": a vault's location maps never became scenes). Pure helpers for rpg_scene's map_location:
what a picture is (its type and size), the art inside a Universal VTT file, and which grid squares
a wall crosses, so arrivals never stand on one."""

from __future__ import annotations

import base64
import binascii
import struct
import math
from collections.abc import Iterable
from typing import Any, Optional

# What a map picture may be (the framework's upload takes the same pictures).
PICTURE_TYPES = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp", "GIF": "image/gif"}
# The largest picture taken (a Dungeondraft export at 200 px a square runs to a few tens of MB).
MAX_PICTURE_BYTES = 64 * 1024 * 1024


class MapError(ValueError):
    """Not a map picture this reads."""


def picture(data: bytes) -> tuple[str, int, int]:
    """A picture's media type and size in pixels, read from its header (no image library); MapError
    when it isn't a PNG, JPEG, WebP or GIF."""
    if not data:
        raise MapError("the picture is empty")
    if len(data) > MAX_PICTURE_BYTES:
        raise MapError(f"the picture is over {MAX_PICTURE_BYTES // (1024 * 1024)} MB")
    found = _png(data) or _gif(data) or _webp(data) or _jpeg(data)
    if found is None:
        raise MapError("not a picture this reads (PNG, JPEG, WebP or GIF)")
    kind, width, height = found
    if width <= 0 or height <= 0:
        raise MapError("the picture has no size")
    return kind, width, height


def _png(data: bytes) -> Optional[tuple[str, int, int]]:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return PICTURE_TYPES["PNG"], width, height


def _gif(data: bytes) -> Optional[tuple[str, int, int]]:
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    width, height = struct.unpack("<HH", data[6:10])
    return PICTURE_TYPES["GIF"], width, height


def _webp(data: bytes) -> Optional[tuple[str, int, int]]:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
    elif chunk == b"VP8 ":
        width, height = struct.unpack("<HH", data[26:30])
        width, height = width & 0x3FFF, height & 0x3FFF
    elif chunk == b"VP8L":
        bits = int.from_bytes(data[21:25], "little")
        width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    else:
        return None
    return PICTURE_TYPES["WEBP"], width, height


def _jpeg(data: bytes) -> Optional[tuple[str, int, int]]:
    if data[:2] != b"\xff\xd8":
        return None
    at = 2
    while at + 9 < len(data):
        if data[at] != 0xFF:
            at += 1
            continue
        marker = data[at + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            at += 2
            continue
        length = struct.unpack(">H", data[at + 2 : at + 4])[0]
        # Start-of-frame markers (not DHT, JPG, DAC) carry the size.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[at + 5 : at + 9])
            return PICTURE_TYPES["JPEG"], width, height
        at += 2 + length
    return None


def decoded(text: Optional[str]) -> Optional[bytes]:
    """Base64 text (a .dd2vtt's "image", or a data: URL's payload) as bytes; None when empty."""
    if not text:
        return None
    payload = text.split(",", 1)[1] if text.startswith("data:") else text
    try:
        return base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError) as error:
        raise MapError("the picture isn't base64") from error


def uvtt_picture(uvtt: dict[str, Any]) -> Optional[bytes]:
    """The art a Universal VTT file carries (its "image", base64), or None."""
    image = uvtt.get("image")
    return decoded(image) if isinstance(image, str) else None


def wall_cells(walls: Iterable[Iterable[Iterable[float]]], grid: float, columns: int, rows: int) -> set[tuple[int, int]]:
    """The grid squares any wall's line passes through (sampled every eighth of a square), so an
    arrival is never put on a wall or a door."""
    blocked: set[tuple[int, int]] = set()
    step = max(1.0, grid / 8)
    for points in walls:
        corners = [(float(one[0]), float(one[1])) for one in points]
        for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
            length = math.hypot(x1 - x0, y1 - y0)
            count = max(1, int(length // step))
            for index in range(count + 1):
                x = x0 + (x1 - x0) * index / count
                y = y0 + (y1 - y0) * index / count
                cell = (int(x // grid), int(y // grid))
                if 0 <= cell[0] < columns and 0 <= cell[1] < rows:
                    blocked.add(cell)
    return blocked
