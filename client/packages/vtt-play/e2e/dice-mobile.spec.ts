// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The 3D dice on a phone (the operator: "Dice box also has no 3d rendering", on a phone browser):
 * DiceStage in a 390 × 844 touch viewport draws a 5e roll's d8 and d20, still draws when it sits in
 * a drawer that opens after the throw, and with no WebGL context hides itself and leaves the
 * result, never an empty box or a broken page. The harness is bundled first (path in DICE_JS).
 */
import { readFileSync } from 'node:fs';
import { expect, test, type Locator, type Page } from '@playwright/test';

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 });

const HARNESS = process.env.DICE_JS ?? '';

async function open(page: Page, mode: string): Promise<string[]> {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.setContent(
    `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
     <style>:root{--muted:240 4.8% 95.9%;--border:240 5.9% 90%;--foreground:240 10% 3.9%;--primary:262 83% 58%;--primary-foreground:0 0% 98%;--card:0 0% 100%;--muted-foreground:240 3.8% 46.1%}body{margin:0;font-family:sans-serif;background:#fff}.hidden{display:none}.h-40{height:10rem}.w-full{width:100%}canvas{display:block}</style>
     </head><body><div id="root"></div></body></html>`,
  );
  await page.evaluate((chosen) => Object.assign(window, { diceMode: chosen }), mode);
  await page.addScriptTag({ content: readFileSync(HARNESS, 'utf8') });
  return errors;
}

/** How many of the element's pixels aren't the white page: a drawn die covers thousands. */
async function inked(page: Page, element: Locator): Promise<number> {
  const shot = (await element.screenshot()).toString('base64');
  return page.evaluate(async (data) => {
    const image = new Image();
    image.src = `data:image/png;base64,${data}`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext('2d')!;
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let at = 0; at < pixels.length; at += 4)
      if (pixels[at]! < 235 || pixels[at + 1]! < 235 || pixels[at + 2]! < 235) count += 1;
    return count;
  }, shot);
}

test('a 5e roll draws its d8 and d20 across the phone', async ({ page }) => {
  const errors = await open(page, 'open');
  const stage = page.locator('canvas[data-dice-stage]');
  await expect(stage).toBeVisible();
  const box = (await stage.boundingBox())!;
  expect(box.width).toBeGreaterThan(300);
  expect(box.height).toBeGreaterThan(100);
  await expect.poll(() => inked(page, stage), { timeout: 15_000 }).toBeGreaterThan(2000);
  expect(errors).toEqual([]);
});

test('the dice still draw in a drawer that opens after the throw', async ({ page }) => {
  const errors = await open(page, 'drawer');
  const stage = page.locator('canvas[data-dice-stage]');
  await expect(stage).toBeVisible({ timeout: 5_000 });
  await expect.poll(() => inked(page, stage), { timeout: 15_000 }).toBeGreaterThan(2000);
  expect(errors).toEqual([]);
});

test('with no WebGL the stage hides and the result stays, the page unbroken', async ({ page }) => {
  const errors = await open(page, 'no-webgl');
  await expect(page.locator('#result')).toHaveText('Total 22');
  await expect(page.locator('canvas[data-dice-stage]')).toBeHidden();
  expect(errors).toEqual([]);
});
