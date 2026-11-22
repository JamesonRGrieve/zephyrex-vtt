// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The map on a phone (the operator: "The map is also completely nonfunctional, at least on mobile"):
 * SceneCanvas in a 390 × 844 touch viewport opens fitted to its width, pans with one finger,
 * pinch-zooms, drags the player's own token from a 44 px target however small it's drawn, and
 * leaves the page scrolling outside it; with a mouse, a wheel over it zooms without scrolling the
 * page. Touches go through CDP, as a phone's would.
 */
import { readFileSync } from 'node:fs';
import { expect, test, type CDPSession, type Page } from '@playwright/test';

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });

const HARNESS = process.env.HARNESS_JS ?? '';

async function open(page: Page): Promise<void> {
  await page.setContent(
    `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
     <style>body{margin:0;font-family:sans-serif}.h-\\[60svh\\]{height:60svh}.min-h-64{min-height:16rem}.w-full{width:100%}.h-full{height:100%}.relative{position:relative}.overflow-hidden{overflow:hidden}.touch-none{touch-action:none}canvas{display:block}</style>
     </head><body><p style="height:120px">Above the map</p><div id="root"></div><p style="height:1200px">Below the map</p></body></html>`,
  );
  await page.addScriptTag({ content: readFileSync(HARNESS, 'utf8') });
  await expect(page.locator('canvas')).toHaveAttribute('data-camera', /.+/);
}

async function camera(page: Page): Promise<{ zoom: number; x: number; y: number }> {
  const [zoom, x, y] = ((await page.locator('canvas').getAttribute('data-camera')) ?? '').split(',').map(Number);
  return { zoom: zoom!, x: x!, y: y! };
}

/** The canvas's top-left on the page. */
async function origin(page: Page): Promise<{ left: number; top: number }> {
  const box = await page.locator('canvas').boundingBox();
  if (!box) throw new Error('no canvas');
  return { left: box.x, top: box.y };
}

async function touch(
  cdp: CDPSession,
  type: 'touchStart' | 'touchMove' | 'touchEnd',
  points: [number, number][],
): Promise<void> {
  await cdp.send('Input.dispatchTouchEvent', {
    type,
    touchPoints: type === 'touchEnd' ? [] : points.map(([x, y], id) => ({ x, y, id })),
  });
}

async function drag(cdp: CDPSession, from: [number, number], to: [number, number]): Promise<void> {
  await touch(cdp, 'touchStart', [from]);
  for (let step = 1; step <= 6; step += 1) {
    const t = step / 6;
    await touch(cdp, 'touchMove', [[from[0] + (to[0] - from[0]) * t, from[1] + (to[1] - from[1]) * t]]);
  }
  await touch(cdp, 'touchEnd', []);
}

/** A scene point's place on the page under the current camera. */
async function onPage(page: Page, x: number, y: number): Promise<[number, number]> {
  const view = await camera(page);
  const at = await origin(page);
  return [at.left + (x - view.x) * view.zoom, at.top + (y - view.y) * view.zoom];
}

test('opens fitted to its width', async ({ page }) => {
  await open(page);
  const view = await camera(page);
  expect(view.zoom).toBeCloseTo(390 / 2000, 3);
  expect(view.x).toBeCloseTo(0, 0);
});

test('drags the player’s own token from a 44 px target, snapped to the grid', async ({ page }) => {
  await open(page);
  const cdp = await page.context().newCDPSession(page);
  // Brann's cell is drawn about 20 px wide; touch 15 px off its right edge, inside the 44 px target.
  const [left, top] = await onPage(page, 1000, 700);
  const cell = 100 * (await camera(page)).zoom;
  const start: [number, number] = [left + cell + 10, top + cell / 2];
  await drag(cdp, start, [start[0] + cell * 2, start[1]]);
  await expect.poll(() => page.evaluate(() => window.moves)).toEqual([{ id: 'brann', x: 1200, y: 700 }]);
});

test('pans with one finger and pinch-zooms', async ({ page }) => {
  await open(page);
  const cdp = await page.context().newCDPSession(page);
  const before = await camera(page);
  const at = await origin(page);
  await drag(cdp, [at.left + 40, at.top + 60], [at.left + 140, at.top + 60]);
  const panned = await camera(page);
  expect(panned.zoom).toBeCloseTo(before.zoom, 4);
  expect(panned.x).toBeLessThan(before.x - 100);
  await touch(cdp, 'touchStart', [
    [at.left + 150, at.top + 200],
    [at.left + 240, at.top + 200],
  ]);
  for (let step = 1; step <= 6; step += 1) {
    await touch(cdp, 'touchMove', [
      [at.left + 150 - step * 12, at.top + 200],
      [at.left + 240 + step * 12, at.top + 200],
    ]);
  }
  await touch(cdp, 'touchEnd', []);
  expect((await camera(page)).zoom).toBeGreaterThan(panned.zoom * 1.5);
  expect(await page.evaluate(() => window.moves)).toEqual([]);
});

test('leaves the page scrolling outside the map', async ({ page }) => {
  await open(page);
  const cdp = await page.context().newCDPSession(page);
  await drag(cdp, [200, 800], [200, 500]);
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(100);
});

test.describe('with a mouse', () => {
  // Mobile emulation sends no wheel events; a desktop page is where a wheel would scroll the page.
  test.use({ viewport: { width: 1024, height: 768 }, hasTouch: false, isMobile: false, deviceScaleFactor: 1 });

  test('a wheel over the map zooms it without scrolling the page', async ({ page }) => {
    await open(page);
    await page.evaluate(() => window.scrollTo(0, 40));
    const scrolled = await page.evaluate(() => window.scrollY);
    const at = await origin(page);
    const before = (await camera(page)).zoom;
    await page.mouse.move(at.left + 100, at.top + 100);
    await page.mouse.wheel(0, -200);
    await expect.poll(async () => (await camera(page)).zoom).toBeGreaterThan(before);
    expect(await page.evaluate(() => window.scrollY)).toBe(scrolled);
  });
});
