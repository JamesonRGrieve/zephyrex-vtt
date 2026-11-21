# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a token perceives in its scene (A23): pure 2D line of sight, the server as referee.

A pure function of plain data, so ``contract/vision-cases.json`` holds it exactly; the scene manager
gathers the data from the records. Coordinates are the scene's pixels, y down. A token's ``x`` and
``y`` are its top-left corner and its ``width`` and ``height`` are in grid cells; ``sight_range`` is
in the scene's distance units (``grid_distance`` per cell, none for unlimited); ``rotation`` is in
degrees clockwise from facing down the screen, and ``sight_angle`` is the cone it sees (360: all
around).

A target is seen when any of its sample points (its centre, and its corners one pixel in) is within
range, inside the cone, and not cut off by a wall from the viewer's centre:

- a wall with ``sight_restriction`` ``none`` never blocks, nor does an open or broken door;
- a ``normal`` wall blocks; ``limited`` walls block only two or more at once (as Foundry's);
- a one-way wall (``direction`` ``left`` or ``right``) blocks only a viewer on that side. For a wall
  drawn from point a to point b, a viewer v is on its left when (b − a) × (v − a) > 0;
- a line only touching a wall's end, or running along it, isn't cut by it.

A hidden token is never seen. A dark scene (no global illumination, darkness 0.5 or more) shows
nothing beyond the viewer until lights (V11) are modelled. A door is seen when its wall's midpoint
is (that wall aside); a secret door is never listed.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]

DARK_FROM = 0.5
SAMPLE_INSET = 1.0
DISTANCE_PLACES = 1
OPEN_DOOR_STATES = frozenset({"open", "broken"})
FULL_CIRCLE = 360.0


@dataclass(frozen=True)
class Token:
    id: str
    x: float
    y: float
    width: float = 1.0
    height: float = 1.0
    rotation: float = 0.0
    sight_range: float | None = None
    sight_angle: float = FULL_CIRCLE
    is_hidden: bool = False


@dataclass(frozen=True)
class Wall:
    id: str
    points: Sequence[Sequence[float]]
    door_type: str = "none"
    door_state: str = "closed"
    sight_restriction: str = "normal"
    direction: str = "both"
    move_restriction: str = "normal"


@dataclass(frozen=True)
class Scene:
    grid_size: float = 100.0
    grid_distance: float = 5.0
    global_illumination: bool = True
    darkness_level: float = 0.0


@dataclass
class Perception:
    viewer: str
    lit: bool
    seen: list[dict[str, Any]] = field(default_factory=list)
    doors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"viewer": self.viewer, "lit": self.lit, "seen": self.seen, "doors": self.doors}


def _center(token: Token, grid: float) -> Point:
    return (token.x + token.width * grid / 2, token.y + token.height * grid / 2)


def _samples(token: Token, grid: float) -> list[Point]:
    right = token.x + token.width * grid - SAMPLE_INSET
    bottom = token.y + token.height * grid - SAMPLE_INSET
    left, top = token.x + SAMPLE_INSET, token.y + SAMPLE_INSET
    return [_center(token, grid), (left, top), (right, top), (left, bottom), (right, bottom)]


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _cuts(p: Point, q: Point, a: Point, b: Point) -> bool:
    """Whether segment p→q properly crosses segment a→b (touching or running along doesn't count)."""
    d1, d2 = _cross(a, b, p), _cross(a, b, q)
    d3, d4 = _cross(p, q, a), _cross(p, q, b)
    return ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4))


def _segments(wall: Wall) -> list[tuple[Point, Point]]:
    points = [(float(point[0]), float(point[1])) for point in wall.points]
    return list(zip(points, points[1:], strict=False))


def _blocks_from(wall: Wall, viewer: Point, a: Point, b: Point) -> bool:
    """Whether this stretch of wall blocks a viewer at ``viewer`` at all (its kind, door and direction)."""
    if wall.sight_restriction == "none":
        return False
    if wall.door_type != "none" and wall.door_state in OPEN_DOOR_STATES:
        return False
    if wall.direction == "both":
        return True
    on_left = _cross(a, b, viewer) > 0
    return on_left if wall.direction == "left" else not on_left


def _clear(viewer: Point, point: Point, walls: Iterable[Wall], skip: str | None = None) -> bool:
    limited = 0
    for wall in walls:
        if wall.id == skip:
            continue
        for a, b in _segments(wall):
            if _cuts(viewer, point, a, b) and _blocks_from(wall, viewer, a, b):
                if wall.sight_restriction == "limited":
                    limited += 1
                    if limited >= 2:
                        return False
                else:
                    return False
                break  # one crossing per wall
    return True


def _in_cone(viewer: Token, origin: Point, point: Point) -> bool:
    if viewer.sight_angle >= FULL_CIRCLE:
        return True
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    if dx == 0 and dy == 0:
        return True
    facing = math.radians(viewer.rotation)
    fx, fy = -math.sin(facing), math.cos(facing)
    cosine = (dx * fx + dy * fy) / math.hypot(dx, dy)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine)))) <= viewer.sight_angle / 2


def perceive(scene: Scene, viewer: Token, tokens: Iterable[Token], walls: Sequence[Wall]) -> Perception:
    """What ``viewer`` sees: the other tokens (nearest first, with their distance) and the doors."""
    lit = scene.global_illumination or scene.darkness_level < DARK_FROM
    perception = Perception(viewer=viewer.id, lit=lit)
    if not lit:
        return perception
    grid = scene.grid_size
    origin = _center(viewer, grid)
    reach = math.inf if viewer.sight_range is None else viewer.sight_range / scene.grid_distance * grid

    def visible(point: Point, skip: str | None = None) -> bool:
        return (
            math.dist(origin, point) <= reach
            and _in_cone(viewer, origin, point)
            and _clear(origin, point, walls, skip)
        )

    seen = []
    for token in tokens:
        if token.id == viewer.id or token.is_hidden:
            continue
        if any(visible(point) for point in _samples(token, grid)):
            distance = round(math.dist(origin, _center(token, grid)) / grid * scene.grid_distance, DISTANCE_PLACES)
            seen.append({"id": token.id, "distance": distance})
    perception.seen = sorted(seen, key=lambda one: (one["distance"], one["id"]))
    for wall in walls:
        if wall.door_type in ("none", "secret"):
            continue
        segments = _segments(wall)
        if not segments:
            continue
        a, b = segments[len(segments) // 2]
        if visible(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), skip=wall.id):
            perception.doors.append(wall.id)
    perception.doors.sort()
    return perception


def blocks_move(start: Point, end: Point, walls: Iterable[Wall]) -> str | None:
    """The wall a move from ``start`` to ``end`` (token centres) would cross, or None. A wall that
    doesn't restrict movement, an open door and the open side of a one-way wall let it through."""
    for wall in walls:
        if wall.move_restriction == "none":
            continue
        if wall.door_type != "none" and wall.door_state in OPEN_DOOR_STATES:
            continue
        for a, b in _segments(wall):
            if not _cuts(start, end, a, b):
                continue
            if wall.direction == "both":
                return wall.id
            on_left = _cross(a, b, start) > 0
            if on_left == (wall.direction == "left"):
                return wall.id
    return None
