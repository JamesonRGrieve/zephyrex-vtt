// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The map on a phone (the operator: "The map is also completely nonfunctional, at least on mobile"):
 * SceneCanvas in a 390 × 844 touch viewport opens on the whole map fitted to its width, pans with one finger,
 * pinch-zooms, drags the player's own token from a 44 px target however small it's drawn, and
 * leaves the page scrolling outside it; with a mouse, a wheel over it zooms without scrolling the
 * page; the measure tool reads a finger's drag in the scene's units; the GM taps a door to open it.
 * Touches go through CDP, as a phone's would.
 */
import { readFileSync } from 'node:fs';
import { expect, test, type CDPSession, type Page } from '@playwright/test';

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });

const HARNESS = process.env.HARNESS_JS ?? '';

async function open(page: Page, withPicture = false, flags: Record<string, unknown> = {}): Promise<void> {
  await page.setContent(
    `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
     <style>:root{--muted:240 4.8% 95.9%;--border:240 5.9% 90%;--foreground:240 10% 3.9%;--primary:262 83% 58%;--primary-foreground:0 0% 98%;--muted-foreground:240 3.8% 46.1%}body{margin:0;font-family:sans-serif}.h-\\[60svh\\]{height:60svh}.min-h-64{min-height:16rem}.w-full{width:100%}.h-full{height:100%}.relative{position:relative}.overflow-hidden{overflow:hidden}.touch-none{touch-action:none}canvas{display:block}</style>
     </head><body><p style="height:120px">Above the map</p><div id="root"></div><p style="height:1200px">Below the map</p></body></html>`,
  );
  if (withPicture) await page.evaluate(() => Object.assign(window, { vttPicture: true }));
  if (Object.keys(flags).length) await page.evaluate((set) => Object.assign(window, set), flags);
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

test('opens on the whole map, in a box shaped like it, on a visible ground (a theme of bare HSL channels)', async ({
  page,
}) => {
  await open(page);
  const view = await camera(page);
  // The 2000 × 1500 scene, its width fitted to the canvas (the operator, 2026-11-24: a town opened
  // zoomed on one token showed a few houses); the box is the scene's shape, so it shows whole.
  const box = (await page.locator('canvas').boundingBox())!;
  expect(view.zoom).toBeCloseTo(box.width / 2000, 3);
  expect(box.height).toBeCloseTo((box.width * 1500) / 2000, 0);
  const ground = await page.evaluate(() => {
    const canvas = document.querySelector('canvas')!;
    const pixel = canvas
      .getContext('2d')!
      .getImageData(Math.round(canvas.width * 0.9), Math.round(canvas.height * 0.5), 1, 1).data;
    return [pixel[0], pixel[1], pixel[2], pixel[3]];
  });
  expect(ground[3]).toBeGreaterThan(0);
  expect(ground[0]! + ground[1]! + ground[2]!).toBeGreaterThan(300); // the light theme's muted ground, not black
});

test('draws the place’s picture under the grid when the scene has no art', async ({ page }) => {
  await open(page, true);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const canvas = document.querySelector('canvas')!;
        const [r, g, b] = canvas
          .getContext('2d')!
          .getImageData(Math.round(canvas.width * 0.9), Math.round(canvas.height * 0.5), 1, 1).data;
        return r! > 150 && g! < 120 && b! < 120;
      }),
    )
    .toBe(true);
});

test('tap a token to select it, then tap a cell to move it there', async ({ page }) => {
  await open(page);
  const [left, top] = await onPage(page, 1050, 750);
  await page.touchscreen.tap(left, top);
  await expect(page.locator('canvas')).toHaveAttribute('data-selected', 'brann');
  const [cellX, cellY] = await onPage(page, 1250, 750);
  await page.touchscreen.tap(cellX, cellY);
  await expect.poll(() => page.evaluate(() => window.moves)).toEqual([{ id: 'brann', x: 1200, y: 700 }]);
  await expect(page.locator('canvas')).toHaveAttribute('data-selected', '');
});

test('the keyboard selects the player’s token and moves it', async ({ page }) => {
  await open(page);
  await page.locator('canvas').focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('canvas')).toHaveAttribute('data-selected', 'brann');
  await page.keyboard.press('ArrowDown');
  await expect.poll(() => page.evaluate(() => window.moves)).toEqual([{ id: 'brann', x: 1000, y: 800 }]);
});

test('drags the player’s own token from a 44 px target, snapped to the grid', async ({ page }) => {
  await open(page);
  const cdp = await page.context().newCDPSession(page);
  // Brann's cell is drawn about 28 px wide; touch 5 px off its right edge, inside the 44 px target.
  const [left, top] = await onPage(page, 1000, 700);
  const cell = 100 * (await camera(page)).zoom;
  const start: [number, number] = [left + cell + 5, top + cell / 2];
  await drag(cdp, start, [start[0] + cell * 2, start[1]]);
  await expect.poll(() => page.evaluate(() => window.moves)).toEqual([{ id: 'brann', x: 1200, y: 700 }]);
});

test('the measure tool reads a drag in the scene’s units, and moves nothing', async ({ page }) => {
  await open(page, false, { vttTool: 'measure' });
  const cdp = await page.context().newCDPSession(page);
  // Three cells east of an empty spot, the cells 5 ft each.
  const from = await onPage(page, 150, 950);
  const to = await onPage(page, 450, 950);
  await drag(cdp, from, to);
  await expect(page.locator('canvas')).toHaveAttribute('data-measure', '15 ft');
  expect(await page.evaluate(() => window.moves)).toEqual([]);
});

test('the GM taps a door to open or close it', async ({ page }) => {
  await open(page, false, { vttGm: true });
  const [left, top] = await onPage(page, 650, 200);
  await page.touchscreen.tap(left, top);
  await expect.poll(() => page.evaluate(() => window.doors)).toEqual(['door']);
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

test('right-click an item for its menu; choosing it runs the host’s action, from Brann’s distance', async ({ page }) => {
  await open(page);
  const [left, top] = await onPage(page, 1050, 1050);
  await page.mouse.click(left, top, { button: 'right' });
  const menu = page.getByRole('menu', { name: 'Actions: Silver key' });
  await expect(menu).toBeVisible();
  await menu.getByRole('menuitem', { name: 'Pick up Silver key' }).click();
  await expect(menu).toBeHidden();
  // Brann stands at (1000, 700): three squares away, 15 ft.
  await expect.poll(() => page.evaluate(() => window.chosen)).toEqual(['item:key:15']);
});

test('long-press a token for its menu; Escape closes it and gives the map back the keys', async ({ page }) => {
  await open(page);
  const cdp = await page.context().newCDPSession(page);
  const [left, top] = await onPage(page, 350, 350);
  await touch(cdp, 'touchStart', [[left, top]]);
  await page.waitForTimeout(800);
  await touch(cdp, 'touchEnd', []);
  const menu = page.getByRole('menu', { name: 'Actions: Innkeeper' });
  await expect(menu).toBeVisible();
  await expect(menu.getByRole('menuitem', { name: 'Talk to Innkeeper' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(menu).toBeHidden();
  await expect(page.locator('canvas')).toBeFocused();
  await expect.poll(() => page.evaluate(() => window.chosen)).toEqual([]);
});

test('right-click an empty square: Move here moves your token through the same move as a drag', async ({ page }) => {
  await open(page);
  const [left, top] = await onPage(page, 1450, 750);
  await page.mouse.click(left, top, { button: 'right' });
  const menu = page.getByRole('menu', { name: 'Actions: This square' });
  await menu.getByRole('menuitem', { name: 'Move here' }).click();
  await expect.poll(() => page.evaluate(() => window.moves)).toEqual([{ id: 'brann', x: 1400, y: 700 }]);
});

test('the keyboard opens the menu at your token (Shift+F10) and moves through it', async ({ page }) => {
  await open(page);
  await page.locator('canvas').focus();
  await page.keyboard.press('Enter');
  await page.keyboard.press('Shift+F10');
  const menu = page.getByRole('menu', { name: 'Actions: Brann' });
  await expect(menu.getByRole('menuitem', { name: 'Talk to Brann' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect.poll(() => page.evaluate(() => window.chosen)).toEqual(['token:brann:0']);
});
