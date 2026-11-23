// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import {
  doorAt,
  fit,
  fitWidth,
  MAX_ZOOM,
  measure,
  MIN_TARGET,
  MIN_ZOOM,
  panBy,
  snap,
  toScene,
  toScreen,
  tokenAt,
  zoomAt,
} from './geometry';

describe('the camera', () => {
  it('maps screen to scene and back', () => {
    const camera = { zoom: 2, x: 100, y: 50 };
    expect(toScene(camera, 40, 20)).toEqual([120, 60]);
    expect(toScreen(camera, 120, 60)).toEqual([40, 20]);
  });

  it('zooms about the pointer, which stays put, within its limits', () => {
    const camera = { zoom: 1, x: 0, y: 0 };
    const zoomed = zoomAt(camera, 2, 200, 100);
    expect(toScene(zoomed, 200, 100)).toEqual(toScene(camera, 200, 100));
    expect(zoomAt(camera, 1000, 0, 0).zoom).toBe(MAX_ZOOM);
    expect(zoomAt(camera, 0.0001, 0, 0).zoom).toBe(MIN_ZOOM);
  });

  it('pans with a drag, and fits a whole scene in the viewport', () => {
    expect(panBy({ zoom: 2, x: 0, y: 0 }, 100, -50)).toEqual({ zoom: 2, x: -50, y: 25 });
    const camera = fit(2000, 1000, [400, 400]);
    expect(camera.zoom).toBe(0.2);
    expect(toScreen(camera, 1000, 500)).toEqual([200, 200]);
  });
});

describe('tokens', () => {
  it('snap to the grid', () => {
    expect(snap(149, 51, 100)).toEqual([100, 100]);
    expect(snap(-40, 260, 100)).toEqual([-0, 300]);
  });

  it('are hit by the topmost under a point', () => {
    const tokens = [
      { id: 'a', x: 0, y: 0, width: 2, height: 2 },
      { id: 'b', x: 100, y: 100, width: 1, height: 1 },
    ];
    expect(tokenAt(tokens, 150, 150, 100)?.id).toBe('b');
    expect(tokenAt(tokens, 50, 50, 100)?.id).toBe('a');
    expect(tokenAt(tokens, 250, 50, 100)).toBeNull();
  });

  it('keep a 44 px target however far out the zoom is', () => {
    const tokens = [{ id: 'a', x: 1000, y: 1000, width: 1, height: 1 }];
    const zoom = 0.2; // a 100-unit cell is 20 px on screen
    expect(tokenAt(tokens, 1110, 1050, 100)).toBeNull();
    expect(tokenAt(tokens, 1110, 1050, 100, MIN_TARGET / zoom)?.id).toBe('a');
    expect(tokenAt(tokens, 1180, 1050, 100, MIN_TARGET / zoom)).toBeNull();
  });
});

describe('fitting to width', () => {
  it('fills a phone’s width and centres a short scene', () => {
    const camera = fitWidth(2000, 1500, [390, 500]);
    expect(camera.zoom).toBeCloseTo(0.195);
    expect(toScreen(camera, 0, 0)[0]).toBeCloseTo(0);
    expect(toScreen(camera, 2000, 0)[0]).toBeCloseTo(390);
    const [, top] = toScreen(camera, 0, 0);
    const [, bottom] = toScreen(camera, 0, 1500);
    expect(top).toBeCloseTo(500 - bottom);
  });

  it('shows the top of a tall scene', () => {
    expect(toScreen(fitWidth(1000, 4000, [390, 500]), 0, 0)[1]).toBeCloseTo(0);
  });
});

describe('the measure tool and doors', () => {
  it('measures in whole cells of the scene’s distance, a diagonal step counting as one', () => {
    expect(measure([0, 0], [300, 0], 100, 5, 'ft')).toEqual({ cells: 3, distance: 15, label: '15 ft' });
    expect(measure([0, 0], [300, 400], 100, 5, 'ft').label).toBe('20 ft');
    expect(measure([50, 50], [90, 60], 100, 5, 'ft').cells).toBe(0);
  });

  it('finds the door nearest a point, ignoring plain walls and doors too far', () => {
    const walls = [
      {
        id: 'wall',
        points: [
          [0, 0],
          [100, 0],
        ],
        door_type: 'none',
      },
      {
        id: 'door',
        points: [
          [200, 0],
          [300, 0],
        ],
        door_type: 'door',
      },
    ];
    expect(doorAt(walls, 250, 10, 44)?.id).toBe('door');
    expect(doorAt(walls, 50, 0, 44)).toBeNull();
    expect(doorAt(walls, 250, 100, 44)).toBeNull();
  });
});
