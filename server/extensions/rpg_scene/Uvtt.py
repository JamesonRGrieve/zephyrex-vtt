# SPDX-License-Identifier: AGPL-3.0-or-later
"""A Universal VTT map (.uvtt / .dd2vtt: Dungeondraft's and Arkenforge's open export, which
zephyr-cartography writes too) as a scene's walls, doors and lights. Pure: the file's JSON goes in
and the records to make come out, in the scene's pixels. Its embedded picture is not read: the art
is the scene's background (an upload, set by link).

- ``resolution``: the map's size in squares and its pixels per square: the scene's size and grid.
- ``line_of_sight`` and ``objects_line_of_sight``: polylines in squares, walls. A long one is cut
  into pieces of at most MAX_WALL_POINTS points sharing their ends; near-collinear points (a traced
  edge's jitter) are dropped first, within SIMPLIFY squares.
- ``portals``: doors, each a wall between its two bounds, closed or open as the file says.
- ``lights``: a light at its position, its range (squares) in the scene's distance units as its dim
  radius and half of it bright; its colour from the file's hex (AARRGGBB or RRGGBB), white as none.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

# The most points one wall may hold (rpg_scene's MAX_WALL_POINTS).
MAX_WALL_POINTS = 256
# How far, in squares, a point may sit off the line it is dropped from.
SIMPLIFY = 0.02


@dataclass
class Imported:
    width: int
    height: int
    grid_size: float
    level: Optional[str]
    walls: list[list[list[float]]] = field(default_factory=list)
    doors: list[dict[str, Any]] = field(default_factory=list)  # {points, door_state}
    lights: list[dict[str, Any]] = field(default_factory=list)  # {x, y, bright, dim, color}


class UvttError(ValueError):
    """The file isn't a Universal VTT map this reads."""


def _point(raw: Any) -> tuple[float, float]:
    if not isinstance(raw, Mapping) or "x" not in raw or "y" not in raw:
        raise UvttError("A point is {x, y}")
    return float(raw["x"]), float(raw["y"])


def _off_line(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    (px, py), (ax, ay), (bx, by) = point, start, end
    dx, dy = bx - ax, by - ay
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return float(((px - ax) ** 2 + (py - ay) ** 2) ** 0.5)
    return abs(dy * px - dx * py + bx * ay - by * ax) / length


def simplify(points: Sequence[tuple[float, float]], tolerance: float = SIMPLIFY) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker: the points a polyline needs, within ``tolerance`` of the rest."""
    if len(points) <= 2:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        worst, at = 0.0, -1
        for index in range(first + 1, last):
            off = _off_line(points[index], points[first], points[last])
            if off > worst:
                worst, at = off, index
        if at >= 0 and worst > tolerance:
            keep[at] = True
            stack.extend([(first, at), (at, last)])
    return [point for point, kept in zip(points, keep) if kept]


def _pieces(points: list[list[float]]) -> list[list[list[float]]]:
    """A polyline cut into walls of at most MAX_WALL_POINTS points, each starting where the last ended."""
    if len(points) <= MAX_WALL_POINTS:
        return [points]
    pieces = []
    start = 0
    while start < len(points) - 1:
        pieces.append(points[start : start + MAX_WALL_POINTS])
        start += MAX_WALL_POINTS - 1
    return pieces


def _colour(raw: Any) -> Optional[str]:
    text = str(raw or "").strip().lstrip("#").lower()
    if len(text) == 8:
        text = text[2:]  # AARRGGBB: the alpha first
    if len(text) != 6 or any(one not in "0123456789abcdef" for one in text):
        return None
    return None if text == "ffffff" else f"#{text}"


def read(uvtt: Mapping[str, Any], grid_distance: float = 5.0) -> Imported:
    """The walls, doors and lights of a Universal VTT map, in pixels of a scene its size."""
    resolution = uvtt.get("resolution")
    if not isinstance(resolution, Mapping):
        raise UvttError("No resolution: not a Universal VTT map")
    per = float(resolution.get("pixels_per_grid") or 0)
    if per <= 0:
        raise UvttError("The map's pixels_per_grid must be above 0")
    origin = _point(resolution.get("map_origin") or {"x": 0, "y": 0})
    columns, rows = _point(resolution.get("map_size") or {})

    def pixels(point: tuple[float, float]) -> list[float]:
        return [round((point[0] - origin[0]) * per, 2), round((point[1] - origin[1]) * per, 2)]

    found = Imported(width=int(round(columns * per)), height=int(round(rows * per)), grid_size=per, level=uvtt.get("level"))
    for key in ("line_of_sight", "objects_line_of_sight"):
        for line in uvtt.get(key) or []:
            if not isinstance(line, Sequence) or isinstance(line, (str, bytes)):
                raise UvttError(f"{key} holds polylines")
            kept = simplify([_point(one) for one in line])
            if len(kept) < 2:
                continue
            found.walls.extend(_pieces([pixels(one) for one in kept]))
    for portal in uvtt.get("portals") or []:
        bounds = portal.get("bounds") if isinstance(portal, Mapping) else None
        if not isinstance(bounds, Sequence) or len(bounds) < 2:
            raise UvttError("A portal has two bounds")
        found.doors.append(
            {"points": [pixels(_point(bounds[0])), pixels(_point(bounds[-1]))], "door_state": "closed" if portal.get("closed", True) else "open"}
        )
    for light in uvtt.get("lights") or []:
        if not isinstance(light, Mapping):
            raise UvttError("A light is an object")
        x, y = pixels(_point(light.get("position") or {}))
        reach = max(0.0, float(light.get("range") or 0)) * grid_distance
        found.lights.append({"x": x, "y": y, "dim": round(reach, 2), "bright": round(reach / 2, 2), "color": _colour(light.get("color"))})
    return found
