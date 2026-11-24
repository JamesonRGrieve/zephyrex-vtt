# SPDX-License-Identifier: AGPL-3.0-or-later
"""A Universal VTT map as a scene's walls, doors and lights (rpg_scene.Uvtt)."""

import pytest
from zephyrex.extensions.rpg_scene.Uvtt import MAX_WALL_POINTS, UvttError, read, simplify

MAP = {
    "format": 0.3,
    "level": "Ground floor",
    "resolution": {"map_origin": {"x": 0, "y": 0}, "map_size": {"x": 22, "y": 17}, "pixels_per_grid": 100},
    "line_of_sight": [
        [{"x": 1, "y": 1}, {"x": 5, "y": 1.001}, {"x": 9, "y": 1}, {"x": 9, "y": 6}],
        [{"x": 2, "y": 2}],
    ],
    "objects_line_of_sight": [[{"x": 12, "y": 12}, {"x": 13, "y": 12}]],
    "portals": [
        {"position": {"x": 9, "y": 8.5}, "bounds": [{"x": 9, "y": 9}, {"x": 9, "y": 8}], "closed": True},
        {"position": {"x": 4, "y": 6}, "bounds": [{"x": 3.5, "y": 6}, {"x": 4.5, "y": 6}], "closed": False},
    ],
    "lights": [
        {"position": {"x": 10.5, "y": 7}, "range": 6, "intensity": 1, "color": "ffffffff"},
        {"position": {"x": 3, "y": 3}, "range": 2, "color": "ffff8800"},
    ],
    "image": "",
}


def test_walls_doors_and_lights_in_the_scenes_pixels() -> None:
    got = read(MAP)
    assert (got.width, got.height, got.grid_size, got.level) == (2200, 1700, 100.0, "Ground floor")
    # The jitter at (5, 1.001) goes; the one-point line is no wall.
    assert got.walls == [[[100.0, 100.0], [900.0, 100.0], [900.0, 600.0]], [[1200.0, 1200.0], [1300.0, 1200.0]]]
    assert got.doors == [
        {"points": [[900.0, 900.0], [900.0, 800.0]], "door_state": "closed"},
        {"points": [[350.0, 600.0], [450.0, 600.0]], "door_state": "open"},
    ]
    assert got.lights == [
        {"x": 1050.0, "y": 700.0, "dim": 30.0, "bright": 15.0, "color": None},
        {"x": 300.0, "y": 300.0, "dim": 10.0, "bright": 5.0, "color": "#ff8800"},
    ]


def test_a_long_wall_is_cut_into_pieces_that_meet() -> None:
    zigzag = [{"x": index * 0.1, "y": (index % 2) * 0.5} for index in range(600)]
    got = read({**MAP, "line_of_sight": [zigzag], "objects_line_of_sight": [], "portals": [], "lights": []})
    assert len(got.walls) == 3 and all(len(one) <= MAX_WALL_POINTS for one in got.walls)
    assert got.walls[0][-1] == got.walls[1][0] and got.walls[1][-1] == got.walls[2][0]
    assert sum(len(one) for one in got.walls) - (len(got.walls) - 1) == 600


def test_simplify_keeps_corners_and_drops_jitter() -> None:
    assert simplify([(0, 0), (1, 0.001), (2, 0), (2, 2)]) == [(0, 0), (2, 0), (2, 2)]


def test_not_a_map_is_refused() -> None:
    with pytest.raises(UvttError):
        read({"format": 0.3})
    with pytest.raises(UvttError):
        read({**MAP, "resolution": {"pixels_per_grid": 0, "map_size": {"x": 1, "y": 1}}})
