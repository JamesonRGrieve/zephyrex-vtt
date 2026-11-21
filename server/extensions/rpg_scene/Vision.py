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


def _touches(p: Point, q: Point, a: Point, b: Point) -> bool:
    """Whether segment p→q meets segment a→b at all: crossing, touching an end, or lying along it."""
    d1, d2 = _cross(a, b, p), _cross(a, b, q)
    d3, d4 = _cross(p, q, a), _cross(p, q, b)
    if ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4)):
        return True

    def on(o: Point, x: Point, y: Point) -> bool:
        return min(o[0], y[0]) <= x[0] <= max(o[0], y[0]) and min(o[1], y[1]) <= x[1] <= max(o[1], y[1])

    return (
        (d1 == 0 and on(a, p, b)) or (d2 == 0 and on(a, q, b)) or (d3 == 0 and on(p, a, q)) or (d4 == 0 and on(p, b, q))
    )


def blocks_move(start: Point, end: Point, walls: Iterable[Wall]) -> str | None:
    """The wall a move from ``start`` to ``end`` (token centres) would cross or touch, or None. A
    wall that doesn't restrict movement, an open door and the open side of a one-way wall let it
    through. Touching counts: a wall through cell centres would otherwise let a token step onto it
    and off the other side, never "crossing" it."""
    for wall in walls:
        if wall.move_restriction == "none":
            continue
        if wall.door_type != "none" and wall.door_state in OPEN_DOOR_STATES:
            continue
        for a, b in _segments(wall):
            if not _touches(start, end, a, b):
                continue
            if wall.direction == "both":
                return wall.id
            side = _cross(a, b, start)
            if side == 0:
                side = -_cross(a, b, end)
            on_left = side > 0
            if on_left == (wall.direction == "left"):
                return wall.id
    return None


def find_path(
    start: Point, goal: Point, grid: float, bounds: tuple[float, float], walls: Sequence[Wall], limit: int = 20000
) -> list[Point] | None:
    """The cells from ``start`` to ``goal`` (both points snap to their cell centres) on a square grid,
    each step to one of the eight neighbours, never across a wall that blocks movement
    (blocks_move) and never outside the scene's bounds (width, height). A diagonal step needs both of
    its orthogonal steps open too, so nothing slips through a corner. Every step counts one cell.
    None when there is no way through, or the search passes ``limit`` cells."""
    import heapq

    width, height = bounds
    columns, rows = max(1, int(width // grid)), max(1, int(height // grid))

    def cell(point: Point) -> tuple[int, int]:
        return (min(columns - 1, max(0, int(point[0] // grid))), min(rows - 1, max(0, int(point[1] // grid))))

    def centre(at: tuple[int, int]) -> Point:
        return ((at[0] + 0.5) * grid, (at[1] + 0.5) * grid)

    def open_step(a: tuple[int, int], b: tuple[int, int]) -> bool:
        return blocks_move(centre(a), centre(b), walls) is None

    begin, end = cell(start), cell(goal)
    frontier: list[tuple[int, int, tuple[int, int]]] = [(0, 0, begin)]
    came: dict[tuple[int, int], tuple[int, int] | None] = {begin: None}
    cost: dict[tuple[int, int], int] = {begin: 0}
    order = 0
    while frontier:
        _, _, here = heapq.heappop(frontier)
        if here == end:
            path = [here]
            while came[path[-1]] is not None:
                path.append(came[path[-1]])  # type: ignore[arg-type]
            return [centre(at) for at in reversed(path)]
        if len(came) > limit:
            return None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                there = (here[0] + dx, here[1] + dy)
                if not (0 <= there[0] < columns and 0 <= there[1] < rows):
                    continue
                if not open_step(here, there):
                    continue
                if dx and dy and not (open_step(here, (here[0] + dx, here[1])) and open_step(here, (here[0], here[1] + dy))):
                    continue
                step = cost[here] + 1
                if step < cost.get(there, step + 1):
                    cost[there] = step
                    came[there] = here
                    order += 1
                    heapq.heappush(frontier, (step + max(abs(end[0] - there[0]), abs(end[1] - there[1])), order, there))
    return None


def _flat_points(points: Sequence[Any]) -> list[Point]:
    if points and isinstance(points[0], (int, float)):
        return [(float(points[index]), float(points[index + 1])) for index in range(0, len(points) - 1, 2)]
    return [(float(one[0]), float(one[1])) for one in points]


def in_shape(point: Point, shape: dict[str, Any]) -> bool:
    """Whether a point lies inside a region shape (the cartography model's form): a polygon
    ({points} as [x, y, …] or [[x, y], …]), a rectangle ({x, y, width, height}) or an ellipse or circle
    ({x, y, radiusX, radiusY} or {x, y, radius}, centred on x, y)."""
    x, y = point
    kind = shape.get("type")
    if kind == "polygon":
        corners = _flat_points(shape.get("points") or [])
        inside = False
        for index, (ax, ay) in enumerate(corners):
            bx, by = corners[index - 1]
            if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / ((by - ay) or 1e-12) + ax:
                inside = not inside
        return inside
    if kind == "rectangle":
        left, top = float(shape.get("x", 0)), float(shape.get("y", 0))
        return left <= x <= left + float(shape.get("width", 0)) and top <= y <= top + float(shape.get("height", 0))
    if kind in ("ellipse", "circle"):
        rx = float(shape.get("radiusX", shape.get("radius", 0)) or 0)
        ry = float(shape.get("radiusY", shape.get("radius", 0)) or 0)
        if rx <= 0 or ry <= 0:
            return False
        return ((x - float(shape.get("x", 0))) / rx) ** 2 + ((y - float(shape.get("y", 0))) / ry) ** 2 <= 1
    return False


def shape_box(shape: dict[str, Any]) -> tuple[float, float, float, float] | None:
    """A shape's bounding box (left, top, right, bottom), for its centre and its size."""
    kind = shape.get("type")
    if kind == "polygon":
        corners = _flat_points(shape.get("points") or [])
        if not corners:
            return None
        xs, ys = [one[0] for one in corners], [one[1] for one in corners]
        return (min(xs), min(ys), max(xs), max(ys))
    if kind == "rectangle":
        left, top = float(shape.get("x", 0)), float(shape.get("y", 0))
        return (left, top, left + float(shape.get("width", 0)), top + float(shape.get("height", 0)))
    if kind in ("ellipse", "circle"):
        rx = float(shape.get("radiusX", shape.get("radius", 0)) or 0)
        ry = float(shape.get("radiusY", shape.get("radius", 0)) or 0)
        cx, cy = float(shape.get("x", 0)), float(shape.get("y", 0))
        return (cx - rx, cy - ry, cx + rx, cy + ry)
    return None
